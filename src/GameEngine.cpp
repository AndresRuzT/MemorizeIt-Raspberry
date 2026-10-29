#include "GameEngine.hpp"
#include <random>
#include <iostream>
#include <string>
#include <iomanip>
#include <sstream>

GameEngine::GameEngine(int screenWidth, int screenHeight, int cameraIndex)
    : screenWidth(screenWidth), screenHeight(screenHeight),
      initialCameraIndex(cameraIndex), vision(cameraIndex, 640, 480) {}

GameEngine::~GameEngine() {
    vision.stop();
    sound.cleanup();

    if (cameraBuffer != nullptr) {
        delete[] cameraBuffer;
        cameraBuffer = nullptr;
    }
    if (cameraTexture.id != 0) {
        UnloadTexture(cameraTexture);
    }
}

void GameEngine::initialize() {
    sound.init();

    // Iniciar captura de cámara USB en hilo separado
    vision.start();

    // Área de la cuadrícula centrada en la pantalla
    float gridSide = std::min(screenWidth, screenHeight) * 0.70f;
    Rectangle gridRect = {
        (screenWidth - gridSide) * 0.5f,
        (screenHeight - gridSide) * 0.52f,
        gridSide,
        gridSide
    };
    grid.initialize(gridRect, 14.0f);

    // Preparar textura para la miniatura de la cámara
    cameraBuffer = new unsigned char[previewWidth * previewHeight * 3];
    Image blankImg = GenImageColor(previewWidth, previewHeight, BLACK);
    cameraTexture = LoadTextureFromImage(blankImg);
    UnloadImage(blankImg);

    // Generar secuencia completa aleatoria
    generateFullSequence(maxRounds);

    state = GameState::START_SCREEN;
    timer = 0.0f;
}

void GameEngine::generateFullSequence(int totalRounds) {
    fullSequence.clear();
    std::random_device rd;
    std::mt19937 gen(rd());
    std::uniform_int_distribution<int> dis(0, 8);

    for (int i = 0; i < totalRounds; ++i) {
        fullSequence.push_back(dis(gen));
    }
}

void GameEngine::startRound(int roundNumber) {
    currentRound = roundNumber;
    playerStep = 0;
    sequenceStep = 0;
    isStepFlashing = false;
    timer = 0.5f;
    currentHoveredPanel = -1;
    hoverDuration = 0.0f;
    state = GameState::SHOW_SEQUENCE;
}

void GameEngine::update(float deltaTime) {
    grid.update(deltaTime);

    // Permitir cambiar de cámara con la tecla 'C'
    if (IsKeyPressed(KEY_C)) {
        vision.cycleCamera();
    }

    // Actualizar textura de la cámara si hay nuevo cuadro disponible
    if (vision.getLatestRGBFrame(cameraBuffer, previewWidth, previewHeight)) {
        UpdateTexture(cameraTexture, cameraBuffer);
    }

    // 1. Obtener posición del puntero (Dedo por visión o Ratón de prueba)
    FingertipData finger = vision.getFingertip();
    if (finger.detected) {
        pointerPos = { finger.normX * screenWidth, finger.normY * screenHeight };
        pointerActive = true;
    } else if (IsMouseButtonDown(MOUSE_BUTTON_LEFT)) {
        // Fallback interactivo con ratón
        pointerPos = GetMousePosition();
        pointerActive = true;
    } else {
        pointerActive = false;
    }

    // 2. Reducir tiempo de cooldown de debounce
    if (debounceCooldown > 0.0f) {
        debounceCooldown -= deltaTime;
    }

    // 3. Máquina de estados
    switch (state) {
        case GameState::START_SCREEN:
            timer += deltaTime;
            if (IsKeyPressed(KEY_SPACE) || (pointerActive && grid.getPanelAtPosition(pointerPos) >= 0)) {
                startRound(1);
            }
            break;

        case GameState::SHOW_SEQUENCE:
            advanceSequenceDisplay(deltaTime);
            break;

        case GameState::PLAYER_TURN:
            handlePlayerInput(deltaTime);
            break;

        case GameState::ROUND_WON:
            timer -= deltaTime;
            if (timer <= 0.0f) {
                if (currentRound >= maxRounds) {
                    state = GameState::VICTORY;
                } else {
                    startRound(currentRound + 1);
                }
            }
            break;

        case GameState::ROUND_FAILED:
            timer -= deltaTime;
            if (timer <= 0.0f) {
                startRound(currentRound);
            }
            break;

        case GameState::VICTORY:
            if (IsKeyPressed(KEY_SPACE) || IsKeyPressed(KEY_ENTER)) {
                generateFullSequence(maxRounds);
                startRound(1);
            }
            break;
    }
}

void GameEngine::advanceSequenceDisplay(float deltaTime) {
    timer -= deltaTime;
    if (timer <= 0.0f) {
        if (!isStepFlashing) {
            if (sequenceStep < currentRound) {
                int panelToFlash = fullSequence[sequenceStep];
                grid.setPanelState(panelToFlash, PanelVisualState::FLASHING, 0.45f);
                sound.playPanelTone(panelToFlash);

                isStepFlashing = true;
                timer = 0.45f;
            } else {
                state = GameState::PLAYER_TURN;
                playerStep = 0;
                currentHoveredPanel = -1;
                hoverDuration = 0.0f;
                debounceCooldown = 0.30f;
            }
        } else {
            isStepFlashing = false;
            sequenceStep++;
            timer = 0.18f;
        }
    }
}

void GameEngine::handlePlayerInput(float deltaTime) {
    int hovered = pointerActive ? grid.getPanelAtPosition(pointerPos) : -1;

    for (int i = 0; i < 9; ++i) {
        if (i == hovered) {
            grid.setPanelState(i, PanelVisualState::HOVERED, 0.05f);
        }
    }

    if (hovered != -1 && debounceCooldown <= 0.0f) {
        if (hovered == currentHoveredPanel) {
            hoverDuration += deltaTime;
            // Requiere 2 segundos continuos con el dedo sobre el panel
            if (hoverDuration >= requiredDwellTime) {
                triggerPanelPress(hovered);
                hoverDuration = 0.0f;
                debounceCooldown = debounceCooldownTime;
            }
        } else {
            currentHoveredPanel = hovered;
            hoverDuration = 0.0f;
        }
    } else {
        currentHoveredPanel = -1;
        hoverDuration = 0.0f;
    }
}

void GameEngine::triggerPanelPress(int panelIndex) {
    int expected = fullSequence[playerStep];

    if (panelIndex == expected) {
        grid.setPanelState(panelIndex, PanelVisualState::PRESSED, 0.35f);
        sound.playPanelTone(panelIndex);
        playerStep++;

        if (playerStep >= currentRound) {
            state = GameState::ROUND_WON;
            timer = 0.85f;
            grid.setAllState(PanelVisualState::SUCCESS, 0.60f);
            sound.playSuccessChime();
        }
    } else {
        state = GameState::ROUND_FAILED;
        timer = 1.0f;
        grid.setAllState(PanelVisualState::ERROR, 0.80f);
        sound.playErrorBuzzer();
    }
}

void GameEngine::draw() {
    ClearBackground(Color{ 14, 18, 26, 255 });

    // Barra superior
    DrawRectangle(0, 0, screenWidth, 55, Color{ 20, 26, 38, 255 });
    DrawLine(0, 55, screenWidth, 55, Color{ 45, 60, 85, 255 });

    DrawText("REACTOR MEMORY", 25, 16, 22, Color{ 160, 215, 255, 255 });

    // Indicadores LED de las 5 rondas
    int ledStartX = screenWidth - 210;
    for (int i = 0; i < maxRounds; ++i) {
        Rectangle ledRect = { static_cast<float>(ledStartX + i * 36), 20, 24, 16 };
        if (i < currentRound - 1 || (state == GameState::ROUND_WON && i == currentRound - 1)) {
            DrawRectangleRec(ledRect, Color{ 50, 230, 120, 255 });
        } else if (i == currentRound - 1 && state != GameState::VICTORY) {
            DrawRectangleRec(ledRect, Color{ 60, 180, 255, 255 });
        } else {
            DrawRectangleRec(ledRect, Color{ 35, 45, 60, 255 });
        }
        DrawRectangleLinesEx(ledRect, 2, Color{ 80, 105, 135, 255 });
    }

    // Dibujar los 9 paneles del reactor
    grid.draw();

    // Si el usuario mantiene el dedo sobre un panel, dibujar barra de carga interna dentro del panel
    if (state == GameState::PLAYER_TURN && currentHoveredPanel != -1 && hoverDuration > 0.0f) {
        Rectangle b = grid.getPanelBounds(currentHoveredPanel);
        float progress = std::min(1.0f, hoverDuration / requiredDwellTime);
        float fillHeight = b.height * progress;
        Rectangle fillRect = { b.x + 4, b.y + b.height - fillHeight - 4, b.width - 8, fillHeight };
        DrawRectangleRec(fillRect, Color{ 0, 230, 255, 70 });
        DrawRectangleLinesEx(b, 3, Color{ 255, 230, 80, 255 });
    }

    // Mensaje central de estado
    std::string statusText = "";
    Color statusColor = WHITE;

    switch (state) {
        case GameState::START_SCREEN:
            statusText = "COLOCA EL DEDO SOBRE UN PANEL O ESPACIO PARA INICIAR";
            statusColor = Color{ 180, 220, 255, 255 };
            break;
        case GameState::SHOW_SEQUENCE:
            statusText = "MEMORIZA EL PATRON...";
            statusColor = Color{ 255, 215, 0, 255 };
            break;
        case GameState::PLAYER_TURN: {
            if (currentHoveredPanel != -1 && hoverDuration > 0.0f) {
                std::ostringstream ss;
                ss << "MANTEN EL DEDO: " << std::fixed << std::setprecision(1) << hoverDuration << "s / " << requiredDwellTime << "s";
                statusText = ss.str();
                statusColor = Color{ 255, 235, 80, 255 };
            } else {
                statusText = "MANTEN EL DEDO 2 SEGUNDOS SOBRE CADA PANEL";
                statusColor = Color{ 80, 235, 255, 255 };
            }
            break;
        }
        case GameState::ROUND_WON:
            statusText = "CORRECTO!";
            statusColor = Color{ 50, 240, 120, 255 };
            break;
        case GameState::ROUND_FAILED:
            statusText = "FALLO EN EL REACTOR! REINTENTANDO...";
            statusColor = Color{ 255, 60, 70, 255 };
            break;
        case GameState::VICTORY:
            statusText = "REACTOR DESBLOQUEADO! PRESIONA ESPACIO";
            statusColor = Color{ 50, 255, 140, 255 };
            break;
    }

    int textW = MeasureText(statusText.c_str(), 20);
    DrawText(statusText.c_str(), (screenWidth - textW) / 2, screenHeight - 48, 20, statusColor);

    // Miniatura de la cámara USB con efecto espejo en esquina inferior izquierda
    int camX = 18;
    int camY = screenHeight - previewHeight - 16;
    DrawRectangle(camX - 3, camY - 3, previewWidth + 6, previewHeight + 6, Color{ 40, 55, 75, 255 });
    DrawTexture(cameraTexture, camX, camY, WHITE);

    // Etiqueta de la cámara y tecla de alternar
    std::string camStatus = vision.getCameraStatusText();
    DrawRectangle(camX, camY + previewHeight - 20, previewWidth, 20, Color{ 10, 15, 22, 210 });
    DrawText(camStatus.c_str(), camX + 4, camY + previewHeight - 16, 11, Color{ 200, 255, 255, 255 });
    DrawText("[C] Cambiar Cam", camX + 4, camY + 4, 11, Color{ 255, 220, 100, 220 });

    // Cursor visual del dedo si está detectado
    if (pointerActive) {
        DrawCircleV(pointerPos, 14.0f, Color{ 0, 255, 220, 180 });
        DrawCircleLines(static_cast<int>(pointerPos.x), static_cast<int>(pointerPos.y), 18.0f, Color{ 255, 255, 255, 230 });

        // Anillo de progreso de los 2 segundos de dwell time
        if (currentHoveredPanel != -1 && hoverDuration > 0.0f) {
            float progress = std::min(1.0f, hoverDuration / requiredDwellTime);
            DrawCircleSector(pointerPos, 26.0f, -90.0f, -90.0f + (progress * 360.0f), 36, Color{ 255, 220, 40, 200 });

            std::ostringstream ss;
            ss << std::fixed << std::setprecision(1) << (requiredDwellTime - hoverDuration) << "s";
            std::string rem = ss.str();
            DrawText(rem.c_str(), static_cast<int>(pointerPos.x + 24), static_cast<int>(pointerPos.y - 12), 16, Color{ 255, 240, 100, 255 });
        }
    }
}
