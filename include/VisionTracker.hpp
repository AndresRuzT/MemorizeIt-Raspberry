#pragma once

#include <opencv2/opencv.hpp>
#include <thread>
#include <mutex>
#include <atomic>

struct FingertipData {
    bool detected{false};
    float normX{0.0f}; // 0.0 (left) to 1.0 (right)
    float normY{0.0f}; // 0.0 (top) to 1.0 (bottom)
};

class VisionTracker {
public:
    VisionTracker(int cameraIndex = 0, int captureWidth = 320, int captureHeight = 240);
    ~VisionTracker();

    bool start();
    void stop();

    // Obtener los datos más recientes de la punta del dedo (Thread-safe)
    FingertipData getFingertip();

    // Copia el frame actual (en formato RGB) para renderizado en Raylib
    bool getLatestRGBFrame(unsigned char* bufferOut, int targetWidth, int targetHeight);

    // Ajuste dinámico de parámetros HSV si se necesita calibrar
    void setHsvRange(int hMin, int hMax, int sMin, int sMax, int vMin, int vMax);

private:
    void captureLoop();
    void processFrame(const cv::Mat& bgrFrame);

    int cameraIndex;
    int captureWidth;
    int captureHeight;

    std::atomic<bool> isRunning{false};
    std::thread workerThread;

    std::mutex dataMutex;
    FingertipData currentFingertip;
    cv::Mat latestRGB;
    bool hasNewFrame{false};

    // Parámetros HSV para detección de piel
    int hMin{0}, hMax{30};
    int sMin{45}, sMax{200};
    int vMin{60}, vMax{255};

    // Suavizado exponencial para reducir temblores
    float smoothX{0.5f};
    float smoothY{0.5f};
    const float smoothingFactor{0.35f}; // 0 = muy suave/lento, 1 = instantáneo
};
