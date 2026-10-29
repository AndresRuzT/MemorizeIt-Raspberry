#pragma once

#include "raylib.h"
#include "GridPanel.hpp"
#include "SoundSystem.hpp"
#include "VisionTracker.hpp"
#include <vector>

enum class GameState {
    START_SCREEN,
    SHOW_SEQUENCE,
    PLAYER_TURN,
    ROUND_WON,
    ROUND_FAILED,
    VICTORY
};

class GameEngine {
public:
    GameEngine(int screenWidth, int screenHeight, int cameraIndex = -1);
    ~GameEngine();

    void initialize();
    void update(float deltaTime);
    void draw();

    void triggerPanelPress(int panelIndex);

private:
    void generateFullSequence(int totalRounds);
    void startRound(int roundNumber);
    void advanceSequenceDisplay(float deltaTime);
    void handlePlayerInput(float deltaTime);

    int screenWidth;
    int screenHeight;
    int initialCameraIndex;

    GameState state{GameState::START_SCREEN};
    GridPanel grid;
    SoundSystem sound;
    VisionTracker vision;

    // Control de secuencia
    const int maxRounds{5};
    int currentRound{1};
    int playerStep{0};
    std::vector<int> fullSequence;

    // Temporizadores de reproducción
    float timer{0.0f};
    int sequenceStep{0};
    bool isStepFlashing{false};

    // Temporizadores de interacción (2 segundos de dwell time requeridos)
    int currentHoveredPanel{-1};
    float hoverDuration{0.0f};
    float debounceCooldown{0.0f};
    const float requiredDwellTime{2.0f}; // 2 segundos continuos con el dedo sobre el panel
    const float debounceCooldownTime{0.60f};

    // Textura para la vista previa de la cámara USB
    Texture2D cameraTexture{};
    unsigned char* cameraBuffer{nullptr};
    int previewWidth{192};
    int previewHeight{144};

    // Posición del cursor en pantalla
    Vector2 pointerPos{-1.0f, -1.0f};
    bool pointerActive{false};
};
