#include "GameEngine.hpp"
#include <random>
#include <iostream>
#include <string>

GameEngine::GameEngine(int screenWidth, int screenHeight)
    : screenWidth(screenWidth), screenHeight(screenHeight) {}

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

    // Iniciar captura en hilo separado (V4L2)
    vision.start();

    // Área de la cuadrícula centrada en la pantalla
    float gridSide = std::min(screenWidth, screenHeight) * 0.70f;
    Rectangle gridRect = {
        (screenWidth - gridSide) * 0.5f,
        (screenHeight - gridSide) * 0.55f,
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
    timer = 0.5f; // Pequeña pausa antes de mostrar
    state = GameState::SHOW_SEQUENCE;
}

void GameEngine::update(float deltaTime) {
    grid.update(deltaTime);

    // Actualizar textura de la cámara si hay nuevo cuadro disponible
    if (vision.getLatestRGBFrame(cameraBuffer, previewWidth, previewHeight)) {
        UpdateTexture(cameraTexture, cameraBuffer);
    }

    // 1. Obtener posición del puntero (Dedo por visión o Ratón de prueba)
    FingertipData finger = vision.getFingertip();
    if (finger.detected) {
        pointerPos = { finger.normX * screenWidth, finger.normY * screenHeight };
        pointerActive = true;
    } else if (IsMouseButtonDown(MOUSE_BUTTON_LEFT) || IsMouseButtonPressed(MOUSE_BUTTON_LEFT)) {
        // Fallback interactivo con ratón para pruebas directas en PC
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
            // Presionar espacio, clic o colocar el dedo para iniciar
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
                // Reintentar la misma ronda
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
            // Encender el panel correspondiente de la ronda
            if (sequenceStep < currentRound) {
                int panelToFlash = fullSequence[sequenceStep];
                grid.setPanelState(panelToFlash, PanelVisualState::FLASHING, 0.40f);
                sound.playPanelTone(panelToFlash);

                isStepFlashing = true;
                timer = 0.40f; // Tiempo encendido
            } else {
                // Secuencia terminada, turno del jugador
                state = GameState::PLAYER_TURN;
                playerStep = 0;
                currentHoveredPanel = -1;
                hoverDuration = 0.0f;
                debounceCooldown = 0.25f;
            }
        } else {
            // Apagar y esperar breve pausa antes del siguiente
            isStepFlashing = false;
            sequenceStep++;
            timer = 0.16f; // Pausa apagado
        }
    }
}

void GameEngine::handlePlayerInput(float deltaTime) {
    int hovered = pointerActive ? grid.getPanelAtPosition(pointerPos) : -1;

    // Resaltar panel bajo el dedo
    for (int i = 0; i < 9; ++i) {
        if (i == hovered) {
            grid.setPanelState(i, PanelVisualState::HOVERED, 0.05f);
        }
    }

    if (hovered != -1 && debounceCooldown <= 0.0f) {
        if (hovered == currentHoveredPanel) {
            hoverDuration += deltaTime;
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
    // Verificar si coincide con el paso esperado de la secuencia
    int expected = fullSequence[playerStep];

    if (panelIndex == expected) {
        // Acierto parcial
        grid.setPanelState(panelIndex, PanelVisualState::PRESSED, 0.25f);
        sound.playPanelTone(panelIndex);
        playerStep++;

        if (playerStep >= currentRound) {
            // ¡Ronda superada!
            state = GameState::ROUND_WON;
            timer = 0.70f;
            grid.setAllState(PanelVisualState::SUCCESS, 0.50f);
            sound.playSuccessChime();
        }
    } else {
        // Fallo: botón equivocado
        state = GameState::ROUND_FAILED;
        timer = 0.90f;
        grid.setAllState(PanelVisualState::ERROR, 0.70f);
        sound.playErrorBuzzer();
    }
}

void GameEngine::draw() {
    // Fondo estilo sala de reactor de nave espacial
    ClearBackground(Color{ 14, 18, 26, 255 });

    // Barra superior de estado
    DrawRectangle(0, 0, screenWidth, 60, Color{ 20, 26, 38, 255 });
    DrawLine(0, 60, screenWidth, 60, Color{ 45, 60, 85, 255 });

    // Título y LEDs de progreso de ronda
    DrawText("REACTOR MEMORY", 30, 18, 24, Color{ 160, 215, 255, 255 });

    // Luces de progreso (5 indicadores LED rectangulares estilo Among Us)
    int ledStartX = screenWidth - 210;
    for (int i = 0; i < maxRounds; ++i) {
        Rectangle ledRect = { static_cast<float>(ledStartX + i * 36), 22, 24, 16 };
        if (i < currentRound - 1 || (state == GameState::ROUND_WON && i == currentRound - 1)) {
            DrawRectangleRec(ledRect, Color{ 50, 230, 120, 255 }); // Verde: superado
        } else if (i == currentRound - 1 && state != GameState::VICTORY) {
            DrawRectangleRec(ledRect, Color{ 60, 180, 255, 255 }); // Azul: en curso
        } else {
            DrawRectangleRec(ledRect, Color{ 35, 45, 60, 255 });   // Apagado
        }
        DrawRectangleLinesEx(ledRect, 2, Color{ 80, 105, 135, 255 });
    }

    // Dibujar los 9 paneles del juego
    grid.draw();

    // Mensajes centrales según el estado del juego
    std::string statusText = "";
    Color statusColor = WHITE;

    switch (state) {
        case GameState::START_SCREEN:
            statusText = "COLOCA EL DEDO O ESPACIO PARA INICIAR";
            statusColor = Color{ 180, 220, 255, 255 };
            break;
        case GameState::SHOW_SEQUENCE:
            statusText = "MEMORIZA EL PATRON...";
            statusColor = Color{ 255, 215, 0, 255 };
            break;
        case GameState::PLAYER_TURN:
            statusText = "TU TURNO: TOCA LOS PANELES EN ORDEN";
            statusColor = Color{ 80, 235, 255, 255 };
            break;
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
    int camX = 20;
    int camY = screenHeight - previewHeight - 20;
    DrawRectangle(camX - 3, camY - 3, previewWidth + 6, previewHeight + 6, Color{ 40, 55, 75, 255 });
    DrawTexture(cameraTexture, camX, camY, WHITE);
    DrawText("CAM (USB)", camX + 6, camY + 6, 12, Color{ 200, 255, 255, 200 });

    // Dibujar el cursor visual del dedo si está detectado
    if (pointerActive) {
        DrawCircleV(pointerPos, 14.0f, Color{ 0, 255, 255, 160 });
        DrawCircleLines(static_cast<int>(pointerPos.x), static_cast<int>(pointerPos.y), 18.0f, Color{ 255, 255, 255, 220 });

        // Si está en hover cargando la pulsación, dibujar anillo de progreso (dwell time)
        if (currentHoveredPanel != -1 && hoverDuration > 0.0f) {
            float progress = std::min(1.0f, hoverDuration / requiredDwellTime);
            DrawCircleSector(pointerPos, 22.0f, -90.0f, -90.0f + (progress * 360.0f), 32, Color{ 255, 255, 0, 190 });
        }
    }
}
