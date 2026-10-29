#pragma once

#include <opencv2/core.hpp>
#include <opencv2/videoio.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/objdetect.hpp>
#include <thread>
#include <mutex>
#include <atomic>
#include <string>
#include <vector>

struct FingertipData {
    bool detected{false};
    float normX{0.0f}; // 0.0 (izq) a 1.0 (der)
    float normY{0.0f}; // 0.0 (arriba) a 1.0 (abajo)
    int rawX{0};
    int rawY{0};
};

class VisionTracker {
public:
    VisionTracker(int cameraIndex = -1, int captureWidth = 640, int captureHeight = 480);
    ~VisionTracker();

    bool start();
    void stop();

    // Cambiar de cámara (ej. presionar 'C')
    void cycleCamera();
    void setCamera(int newIndex);
    int getCameraIndex() const;
    std::string getCameraStatusText();

    // Obtener los datos más recientes de la punta del dedo (Thread-safe)
    FingertipData getFingertip();

    // Copia el frame actual (en formato RGB) para renderizado en Raylib
    bool getLatestRGBFrame(unsigned char* bufferOut, int targetWidth, int targetHeight);

    // Ajuste dinámico de parámetros HSV si se necesita calibrar
    void setHsvRange(int hMin, int hMax, int sMin, int sMax, int vMin, int vMax);

private:
    void captureLoop();
    void processFrame(const cv::Mat& bgrFrame);
    int detectBestCamera();

    int cameraIndex{-1};
    int captureWidth{640};
    int captureHeight{480};

    std::atomic<bool> isRunning{false};
    std::atomic<bool> needsCameraReopen{false};
    std::thread workerThread;

    std::mutex dataMutex;
    FingertipData currentFingertip;
    cv::Mat latestRGB;
    bool hasNewFrame{false};
    std::string cameraStatus{"Iniciando..."};

    // Clasificador para suprimir rostros
    cv::CascadeClassifier faceCascade;
    std::vector<cv::Rect> lastDetectedFaces;
    int frameCounter{0};

    // Parámetros HSV para detección de piel
    int hMin{0}, hMax{25};
    int sMin{45}, sMax{220};
    int vMin{50}, vMax{255};

    // Suavizado exponencial para evitar saltos bruscos
    float smoothX{0.5f};
    float smoothY{0.5f};
    const float smoothingFactor{0.30f};
};
