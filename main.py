#!/usr/bin/env python3
import sys
import argparse
import pygame
from memorizeit.game import GameEngine

def main():
    parser = argparse.ArgumentParser(description="MemorizeIt - Among Us Reactor Memory (Raspberry Pi 4)")
    parser.add_argument("--cam", type=int, default=None, help="Índice de la cámara USB (ej. 2)")
    parser.add_argument("cam_positional", type=int, nargs="?", default=None, help="Índice opcional posicional")
    args = parser.parse_args()

    chosen_cam = args.cam if args.cam is not None else args.cam_positional

    screen_w = 800
    screen_h = 600

    pygame.init()
    pygame.display.set_caption("MemorizeIt - Among Us Reactor (Python / Raspberry Pi 4)")
    screen = pygame.display.set_mode((screen_w, screen_h))
    clock = pygame.time.Clock()

    game = GameEngine(screen_width=screen_w, screen_height=screen_h, camera_index=chosen_cam)
    game.initialize()

    running = True
    while running:
        dt = clock.tick(60) / 1000.0  # Delta time en segundos (60 FPS objetivo)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False
            else:
                game.handle_event(event)

        pointer_active, pointer_pos = game.update(dt)

        game.draw(screen, pointer_active, pointer_pos)
        pygame.display.flip()

    game.cleanup()
    pygame.quit()
    sys.exit(0)

if __name__ == "__main__":
    main()
