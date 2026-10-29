#!/usr/bin/env python3
import sys
import os
from pathlib import Path

# Auto-reexec into .venv if not already running in it (ensures MediaPipe is available)
_venv_python = (Path(__file__).parent / ".venv" / "bin" / "python").absolute()
if not _venv_python.exists():
    _alt_venv = Path("/home/andres/Documents/OwnProjects/MazeHaus-Raspberry/.venv/bin/python").absolute()
    if _alt_venv.exists():
        _venv_python = _alt_venv

if _venv_python.exists() and Path(sys.executable).absolute() != _venv_python:
    os.execv(str(_venv_python), [str(_venv_python)] + sys.argv)

import argparse
import pygame
from memorizeit.game import GameEngine

def main():
    parser = argparse.ArgumentParser(description="MemorizeIt - Among Us Reactor Memory (Raspberry Pi 4)")
    parser.add_argument("--cam", type=int, default=None, help="Índice de la cámara (ej. 2 para USB, 0 para integrada)")
    parser.add_argument("cam_positional", type=int, nargs="?", default=None, help="Índice opcional posicional")
    args = parser.parse_args()

    chosen_cam = args.cam if args.cam is not None else args.cam_positional

    # Resolución panorámica HD 1280x720 (tablero a la izquierda, cámara a la derecha)
    screen_w = 1280
    screen_h = 720

    pygame.init()
    pygame.display.set_caption("MemorizeIt - [Raspberry Pi 4]")
    screen = pygame.display.set_mode((screen_w, screen_h))
    clock = pygame.time.Clock()

    game = GameEngine(screen_width=screen_w, screen_height=screen_h, camera_index=chosen_cam)
    game.initialize()

    running = True
    while running:
        dt = clock.tick(60) / 1000.0  # 60 FPS estables

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False
            else:
                game.handle_event(event)

        pointer_active, norm_x, norm_y = game.update(dt)

        game.draw(screen, pointer_active, norm_x, norm_y)
        pygame.display.flip()

    game.cleanup()
    pygame.quit()
    sys.exit(0)

if __name__ == "__main__":
    main()
