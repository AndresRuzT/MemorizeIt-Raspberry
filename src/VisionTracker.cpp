#include "VisionTracker.hpp"
#include <iostream>
#include <algorithm>

VisionTracker::VisionTracker(int cameraIndex, int captureWidth, int captureHeight)
    : cameraIndex(cameraIndex), captureWidth(captureWidth), captureHeight(captureHeight) {}

VisionTracker::~VisionTracker() {
    stop();
}

bool VisionTracker::start() {
    if (isRunning) return true;
    isRunning = true;
    workerThread = std::thread(&VisionTracker::captureLoop, this);
    return true;
}

void VisionTracker::stop() {
    if (!isRunning) return;
    isRunning = false;
    if (workerThread.joinable()) {
        workerThread.join();
    }
}

FingertipData VisionTracker::getFingertip() {
    std::lock_guard<std::mutex> lock(dataMutex);
    return currentFingertip;
}

bool VisionTracker::getLatestRGBFrame(unsigned char* bufferOut, int targetWidth, int targetHeight) {
    std::lock_guard<std::mutex> lock(dataMutex);
    if (!hasNewFrame || latestRGB.empty()) return false;

    cv::Mat resized;
    cv::resize(latestRGB, resized, cv::Size(targetWidth, targetHeight), 0, 0, cv::INTER_NEAREST);
    std::memcpy(bufferOut, resized.data, targetWidth * targetHeight * 3);
    hasNewFrame = false;
    return true;
}

void VisionTracker::setHsvRange(int hMin_, int hMax_, int sMin_, int sMax_, int vMin_, int vMax_) {
    std::lock_guard<std::mutex> lock(dataMutex);
    hMin = hMin_; hMax = hMax_;
    sMin = sMin_; sMax = sMax_;
    vMin = vMin_; vMax = vMax_;
}

void VisionTracker::captureLoop() {
    // Intentar abrir con backend V4L2 para Raspberry Pi / Linux
    cv::VideoCapture cap(cameraIndex, cv::CAP_V4L2);
    if (!cap.isOpened()) {
        std::cerr << "[VisionTracker] No se pudo abrir con V4L2. Intentando backend default..." << std::endl;
        cap.open(cameraIndex, cv::CAP_ANY);
    }

    if (!cap.isOpened()) {
        std::cerr << "[VisionTracker] ERROR: No se detectó ninguna cámara USB en el índice " << cameraIndex << std::endl;
        isRunning = false;
        return;
    }

    // Configurar resolución liviana y formato MJPG para no saturar el bus USB de la Raspberry Pi 4
    cap.set(cv::CAP_PROP_FOURCC, cv::VideoWriter::fourcc('M', 'J', 'P', 'G'));
    cap.set(cv::CAP_PROP_FRAME_WIDTH, captureWidth);
    cap.set(cv::CAP_PROP_FRAME_HEIGHT, captureHeight);
    cap.set(cv::CAP_PROP_FPS, 30);

    cv::Mat rawFrame;

    while (isRunning) {
        if (!cap.read(rawFrame) || rawFrame.empty()) {
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
            continue;
        }

        // Efecto espejo horizontal para que la interacción sea natural
        cv::Mat mirrorFrame;
        cv::flip(rawFrame, mirrorFrame, 1);

        processFrame(mirrorFrame);
    }

    cap.release();
}

void VisionTracker::processFrame(const cv::Mat& bgrFrame) {
    cv::Mat hsv, mask;
    cv::cvtColor(bgrFrame, hsv, cv::COLOR_BGR2HSV);

    int curHMin, curHMax, curSMin, curSMax, curVMin, curVMax;
    {
        std::lock_guard<std::mutex> lock(dataMutex);
        curHMin = hMin; curHMax = hMax;
        curSMin = sMin; curSMax = sMax;
        curVMin = vMin; curVMax = vMax;
    }

    // Máscara de tono de piel / dedo
    cv::inRange(hsv, cv::Scalar(curHMin, curSMin, curVMin), cv::Scalar(curHMax, curSMax, curVMax), mask);

    // Operaciones morfológicas para eliminar ruido granular (3x3 kernel)
    cv::Mat kernel = cv::getStructuringElement(cv::MORPH_ELLIPSE, cv::Size(3, 3));
    cv::erode(mask, mask, kernel, cv::Point(-1, -1), 1);
    cv::dilate(mask, mask, kernel, cv::Point(-1, -1), 2);

    // Detección de contornos
    std::vector<std::vector<cv::Point>> contours;
    cv::findContours(mask, contours, cv::RETR_EXTERNAL, cv::CHAIN_APPROX_SIMPLE);

    double maxArea = 0;
    int bestContourIdx = -1;

    for (size_t i = 0; i < contours.size(); ++i) {
        double area = cv::contourArea(contours[i]);
        // Filtro de área mínima para evitar falsos positivos
        if (area > 800.0 && area > maxArea) {
            maxArea = area;
            bestContourIdx = static_cast<int>(i);
        }
    }

    FingertipData result;
    if (bestContourIdx >= 0) {
        const auto& bestContour = contours[bestContourIdx];

        // El punto más alto (menor coordenada Y) representa la punta del dedo
        cv::Point topPoint = bestContour[0];
        for (const auto& pt : bestContour) {
            if (pt.y < topPoint.y) {
                topPoint = pt;
            }
        }

        float rawNormX = static_cast<float>(topPoint.x) / static_cast<float>(bgrFrame.cols);
        float rawNormY = static_cast<float>(topPoint.y) / static_cast<float>(bgrFrame.rows);

        // Filtro de suavizado exponencial
        smoothX = smoothX * (1.0f - smoothingFactor) + rawNormX * smoothingFactor;
        smoothY = smoothY * (1.0f - smoothingFactor) + rawNormY * smoothingFactor;

        result.detected = true;
        result.normX = smoothX;
        result.normY = smoothY;
    } else {
        result.detected = false;
    }

    // Preparar imagen RGB para la vista previa en la interfaz
    cv::Mat rgbFrame;
    cv::cvtColor(bgrFrame, rgbFrame, cv::COLOR_BGR2RGB);

    // Si se detectó el dedo, dibujar un marcador en la vista previa
    if (result.detected) {
        int px = static_cast<int>(result.normX * rgbFrame.cols);
        int py = static_cast<int>(result.normY * rgbFrame.rows);
        cv::circle(rgbFrame, cv::Point(px, py), 6, cv::Scalar(0, 255, 255), -1);
    }

    {
        std::lock_guard<std::mutex> lock(dataMutex);
        currentFingertip = result;
        latestRGB = rgbFrame;
        hasNewFrame = true;
    }
}
