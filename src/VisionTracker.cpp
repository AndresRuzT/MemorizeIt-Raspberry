#include "VisionTracker.hpp"
#include <iostream>
#include <algorithm>
#include <sstream>

VisionTracker::VisionTracker(int cameraIndex, int captureWidth, int captureHeight)
    : cameraIndex(cameraIndex), captureWidth(captureWidth), captureHeight(captureHeight) {
    // Cargar clasificador de rostros para suprimirlos activamente
    const std::vector<std::string> cascadePaths = {
        "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml",
        "/usr/share/opencv/haarcascades/haarcascade_frontalface_default.xml",
        "haarcascade_frontalface_default.xml"
    };

    for (const auto& path : cascadePaths) {
        if (faceCascade.load(path)) {
            std::cout << "[VisionTracker] Clasificador de rostros cargado para supresión: " << path << std::endl;
            break;
        }
    }
}

VisionTracker::~VisionTracker() {
    stop();
}

int VisionTracker::detectBestCamera() {
    // Priorizar cámaras USB externas (índices 2, 1, 3) sobre la webcam integrada (índice 0)
    const std::vector<int> candidates = { 2, 1, 0, 3, 4 };
    for (int idx : candidates) {
        cv::VideoCapture testCap(idx, cv::CAP_V4L2);
        if (!testCap.isOpened()) {
            testCap.open(idx, cv::CAP_ANY);
        }
        if (testCap.isOpened()) {
            cv::Mat testFrame;
            if (testCap.read(testFrame) && !testFrame.empty()) {
                testCap.release();
                std::cout << "[VisionTracker] Cámara seleccionada automáticamente: /dev/video" << idx << std::endl;
                return idx;
            }
            testCap.release();
        }
    }
    return 0;
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

void VisionTracker::cycleCamera() {
    int nextIdx = (cameraIndex + 1) % 4;
    setCamera(nextIdx);
}

void VisionTracker::setCamera(int newIndex) {
    cameraIndex = newIndex;
    needsCameraReopen = true;
}

int VisionTracker::getCameraIndex() const {
    return cameraIndex;
}

std::string VisionTracker::getCameraStatusText() {
    std::lock_guard<std::mutex> lock(dataMutex);
    return cameraStatus;
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
    if (cameraIndex < 0) {
        cameraIndex = detectBestCamera();
    }

    cv::VideoCapture cap;

    auto openDevice = [&](int devIdx) -> bool {
        if (cap.isOpened()) cap.release();
        cap.open(devIdx, cv::CAP_V4L2);
        if (!cap.isOpened()) {
            cap.open(devIdx, cv::CAP_ANY);
        }
        if (cap.isOpened()) {
            cap.set(cv::CAP_PROP_FOURCC, cv::VideoWriter::fourcc('M', 'J', 'P', 'G'));
            cap.set(cv::CAP_PROP_FRAME_WIDTH, captureWidth);
            cap.set(cv::CAP_PROP_FRAME_HEIGHT, captureHeight);
            cap.set(cv::CAP_PROP_FPS, 30);
            return true;
        }
        return false;
    };

    if (!openDevice(cameraIndex)) {
        // Fallback al mejor dispositivo disponible
        cameraIndex = detectBestCamera();
        openDevice(cameraIndex);
    }

    {
        std::lock_guard<std::mutex> lock(dataMutex);
        std::ostringstream ss;
        ss << "CAM [" << cameraIndex << "] " << (cap.isOpened() ? "Conectada" : "Error");
        cameraStatus = ss.str();
    }

    cv::Mat rawFrame;

    while (isRunning) {
        if (needsCameraReopen) {
            needsCameraReopen = false;
            openDevice(cameraIndex);
            std::lock_guard<std::mutex> lock(dataMutex);
            std::ostringstream ss;
            ss << "CAM [" << cameraIndex << "] " << (cap.isOpened() ? "Conectada" : "Sin senal");
            cameraStatus = ss.str();
        }

        if (!cap.isOpened() || !cap.read(rawFrame) || rawFrame.empty()) {
            std::this_thread::sleep_for(std::chrono::milliseconds(20));
            continue;
        }

        // Efecto espejo horizontal para que mover la mano a la derecha se vea a la derecha
        cv::Mat mirrorFrame;
        cv::flip(rawFrame, mirrorFrame, 1);

        processFrame(mirrorFrame);
    }

    if (cap.isOpened()) {
        cap.release();
    }
}

void VisionTracker::processFrame(const cv::Mat& bgrFrame) {
    frameCounter++;

    // 1. Detección periódica de rostros para supresión (cada 4 frames a baja resolución para ahorro de CPU)
    if (!faceCascade.empty() && (frameCounter % 4 == 0 || lastDetectedFaces.empty())) {
        cv::Mat smallGray;
        cv::cvtColor(bgrFrame, smallGray, cv::COLOR_BGR2GRAY);
        cv::resize(smallGray, smallGray, cv::Size(160, 120), 0, 0, cv::INTER_LINEAR);
        cv::equalizeHist(smallGray, smallGray);

        std::vector<cv::Rect> faces;
        faceCascade.detectMultiScale(smallGray, faces, 1.15, 3, 0, cv::Size(25, 25));

        float scaleX = static_cast<float>(bgrFrame.cols) / 160.0f;
        float scaleY = static_cast<float>(bgrFrame.rows) / 120.0f;

        lastDetectedFaces.clear();
        for (const auto& f : faces) {
            cv::Rect scaledFace(
                static_cast<int>(f.x * scaleX),
                static_cast<int>(f.y * scaleY),
                static_cast<int>(f.width * scaleX),
                static_cast<int>(f.height * scaleY)
            );
            // Expandir un 25% el área del rostro para cubrir barbilla y orejas
            int expandW = static_cast<int>(scaledFace.width * 0.25f);
            int expandH = static_cast<int>(scaledFace.height * 0.35f);
            scaledFace.x = std::max(0, scaledFace.x - expandW / 2);
            scaledFace.y = std::max(0, scaledFace.y - expandH / 2);
            scaledFace.width = std::min(bgrFrame.cols - scaledFace.x, scaledFace.width + expandW);
            scaledFace.height = std::min(bgrFrame.rows - scaledFace.y, scaledFace.height + expandH);

            lastDetectedFaces.push_back(scaledFace);
        }
    }

    // 2. Filtrado de piel en espacio HSV
    cv::Mat hsv, skinMask;
    cv::cvtColor(bgrFrame, hsv, cv::COLOR_BGR2HSV);

    int curHMin, curHMax, curSMin, curSMax, curVMin, curVMax;
    {
        std::lock_guard<std::mutex> lock(dataMutex);
        curHMin = hMin; curHMax = hMax;
        curSMin = sMin; curSMax = sMax;
        curVMin = vMin; curVMax = vMax;
    }

    cv::inRange(hsv, cv::Scalar(curHMin, curSMin, curVMin), cv::Scalar(curHMax, curSMax, curVMax), skinMask);

    // 3. SUPRESIÓN ESTRICTA DE ROSTROS: Borrar completamente cualquier rostro de la máscara de piel
    for (const auto& faceBox : lastDetectedFaces) {
        if (faceBox.x >= 0 && faceBox.y >= 0 &&
            faceBox.x + faceBox.width <= skinMask.cols &&
            faceBox.y + faceBox.height <= skinMask.rows) {
            skinMask(faceBox).setTo(0); // Poner en negro absoluto el rostro
        }
    }

    // 4. Morfología para eliminar ruido y aislar la mano
    cv::Mat kernel = cv::getStructuringElement(cv::MORPH_ELLIPSE, cv::Size(5, 5));
    cv::erode(skinMask, skinMask, kernel, cv::Point(-1, -1), 1);
    cv::dilate(skinMask, skinMask, kernel, cv::Point(-1, -1), 2);

    // 5. Encontrar contornos de mano/dedo
    std::vector<std::vector<cv::Point>> contours;
    cv::findContours(skinMask, contours, cv::RETR_EXTERNAL, cv::CHAIN_APPROX_SIMPLE);

    double maxArea = 0;
    int bestContourIdx = -1;

    for (size_t i = 0; i < contours.size(); ++i) {
        double area = cv::contourArea(contours[i]);
        // Ignorar manchas pequeñas o ruidos menores a 1200 px
        if (area > 1200.0 && area > maxArea) {
            maxArea = area;
            bestContourIdx = static_cast<int>(i);
        }
    }

    FingertipData result;
    if (bestContourIdx >= 0) {
        const auto& bestContour = contours[bestContourIdx];

        // La punta del dedo índice es el punto más alto (menor coordenada Y) de la mano extendida
        cv::Point topPoint = bestContour[0];
        for (const auto& pt : bestContour) {
            if (pt.y < topPoint.y) {
                topPoint = pt;
            }
        }

        float rawNormX = static_cast<float>(topPoint.x) / static_cast<float>(bgrFrame.cols);
        float rawNormY = static_cast<float>(topPoint.y) / static_cast<float>(bgrFrame.rows);

        // Suavizado exponencial para estabilidad
        smoothX = smoothX * (1.0f - smoothingFactor) + rawNormX * smoothingFactor;
        smoothY = smoothY * (1.0f - smoothingFactor) + rawNormY * smoothingFactor;

        result.detected = true;
        result.normX = smoothX;
        result.normY = smoothY;
        result.rawX = topPoint.x;
        result.rawY = topPoint.y;
    } else {
        result.detected = false;
    }

    // 6. Preparar imagen RGB para la vista previa en la interfaz
    cv::Mat rgbFrame;
    cv::cvtColor(bgrFrame, rgbFrame, cv::COLOR_BGR2RGB);

    // Dibujar recuadro de rostro suprimido (en rojo tenue) para que el usuario confirme que está bloqueado
    for (const auto& faceBox : lastDetectedFaces) {
        cv::rectangle(rgbFrame, faceBox, cv::Scalar(255, 60, 60), 2);
        cv::putText(rgbFrame, "ROSTRO IGNORADO", cv::Point(faceBox.x + 4, faceBox.y - 6),
                    cv::FONT_HERSHEY_PLAIN, 1.0, cv::Scalar(255, 80, 80), 1);
    }

    // Dibujar la punta del dedo detectada en verde brillante
    if (result.detected) {
        int px = static_cast<int>(result.normX * rgbFrame.cols);
        int py = static_cast<int>(result.normY * rgbFrame.rows);
        cv::circle(rgbFrame, cv::Point(px, py), 9, cv::Scalar(0, 255, 120), -1);
        cv::circle(rgbFrame, cv::Point(px, py), 15, cv::Scalar(255, 255, 255), 2);
        cv::putText(rgbFrame, "DEDO", cv::Point(px + 12, py + 5),
                    cv::FONT_HERSHEY_PLAIN, 1.1, cv::Scalar(0, 255, 120), 2);
    }

    {
        std::lock_guard<std::mutex> lock(dataMutex);
        currentFingertip = result;
        latestRGB = rgbFrame;
        hasNewFrame = true;
    }
}
