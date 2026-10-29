#include "raylib.h"
#include "GameEngine.hpp"
#include <iostream>

int main() {
    const int screenWidth = 800;
    const int screenHeight = 600;

    // Configuración para Raspberry Pi / Linux desktop
    SetConfigFlags(FLAG_VSYNC_HINT | FLAG_MSAA_4X_HINT);
    InitWindow(screenWidth, screenHeight, "MemorizeIt - Among Us Reactor (Raspberry Pi 4)");
    SetTargetFPS(60);

    GameEngine game(screenWidth, screenHeight);
    game.initialize();

    while (!WindowShouldClose()) {
        float dt = GetFrameTime();

        game.update(dt);

        BeginDrawing();
        game.draw();
        DrawFPS(screenWidth - 85, screenHeight - 28);
        EndDrawing();
    }

    CloseWindow();
    return 0;
}
