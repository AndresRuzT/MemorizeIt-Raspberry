import pygame
import random
import math
from .grid import GridPanel, PanelState
from .vision import VisionTracker
from .audio import SoundSystem

class GameState:
    START_SCREEN = 0
    SHOW_SEQUENCE = 1
    PLAYER_TURN = 2
    ROUND_WON = 3
    ROUND_FAILED = 4
    VICTORY = 5

class GameEngine:
    def __init__(self, screen_width=800, screen_height=600, camera_index=None):
        self.screen_width = screen_width
        self.screen_height = screen_height

        self.vision = VisionTracker(camera_index=camera_index, width=640, height=480)
        self.sound = SoundSystem()

        # Configuración de la cuadrícula
        grid_side = min(screen_width, screen_height) * 0.70
        grid_rect = pygame.Rect(
            (screen_width - grid_side) * 0.5,
            (screen_height - grid_side) * 0.52,
            grid_side,
            grid_side
        )
        self.grid = GridPanel(grid_rect, spacing=14)

        # Reglas del juego
        self.max_rounds = 5
        self.current_round = 1
        self.player_step = 0
        self.full_sequence = []

        self.state = GameState.START_SCREEN
        self.timer = 0.0

        # Reproducción de secuencia
        self.sequence_step = 0
        self.is_step_flashing = False

        # Temporizador de interacción: 2.0 SEGUNDOS REQUERIDOS
        self.required_dwell_time = 2.0
        self.hover_duration = 0.0
        self.current_hovered_panel = -1
        self.debounce_cooldown = 0.0
        self.debounce_cooldown_time = 0.50

        # Dimensiones de la vista previa de la cámara
        self.preview_w = 192
        self.preview_h = 144
        self.cam_x = 18
        self.cam_y = screen_height - self.preview_h - 18

        # Tipografías
        self.font_large = None
        self.font_med = None
        self.font_small = None

    def initialize(self):
        self.sound.init()
        self.vision.start()
        self.generate_full_sequence(self.max_rounds)

        pygame.font.init()
        self.font_large = pygame.font.SysFont("sans-serif", 24, bold=True)
        self.font_med = pygame.font.SysFont("sans-serif", 20, bold=True)
        self.font_small = pygame.font.SysFont("sans-serif", 13, bold=True)

    def generate_full_sequence(self, total_rounds):
        self.full_sequence = [random.randint(0, 8) for _ in range(total_rounds)]

    def start_round(self, round_num):
        self.current_round = round_num
        self.player_step = 0
        self.sequence_step = 0
        self.is_step_flashing = False
        self.timer = 0.5
        self.current_hovered_panel = -1
        self.hover_duration = 0.0
        self.state = GameState.SHOW_SEQUENCE

    def update(self, dt):
        self.grid.update(dt)

        if self.debounce_cooldown > 0.0:
            self.debounce_cooldown -= dt

        # Posición del cursor (Dedo o ratón)
        finger = self.vision.get_fingertip()
        pointer_active = False
        pointer_pos = (-1, -1)

        if finger.detected:
            pointer_pos = (int(finger.norm_x * self.screen_width), int(finger.norm_y * self.screen_height))
            pointer_active = True
        elif pygame.mouse.get_pressed()[0]:
            pointer_pos = pygame.mouse.get_pos()
            pointer_active = True

        # Máquina de estados
        if self.state == GameState.START_SCREEN:
            self.timer += dt
            if pointer_active and self.grid.get_panel_at(pointer_pos) >= 0:
                self.start_round(1)

        elif self.state == GameState.SHOW_SEQUENCE:
            self._update_show_sequence(dt)

        elif self.state == GameState.PLAYER_TURN:
            self._update_player_turn(dt, pointer_active, pointer_pos)

        elif self.state == GameState.ROUND_WON:
            self.timer -= dt
            if self.timer <= 0.0:
                if self.current_round >= self.max_rounds:
                    self.state = GameState.VICTORY
                else:
                    self.start_round(self.current_round + 1)

        elif self.state == GameState.ROUND_FAILED:
            self.timer -= dt
            if self.timer <= 0.0:
                self.start_round(self.current_round)

        return pointer_active, pointer_pos

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_c:
                self.vision.cycle_camera()
            elif event.key in (pygame.K_SPACE, pygame.K_RETURN):
                if self.state == GameState.START_SCREEN:
                    self.start_round(1)
                elif self.state == GameState.VICTORY:
                    self.generate_full_sequence(self.max_rounds)
                    self.start_round(1)

    def _update_show_sequence(self, dt):
        self.timer -= dt
        if self.timer <= 0.0:
            if not self.is_step_flashing:
                if self.sequence_step < self.current_round:
                    panel_to_flash = self.full_sequence[self.sequence_step]
                    self.grid.set_panel_state(panel_to_flash, PanelState.FLASHING, duration=0.45)
                    self.sound.play_panel_tone(panel_to_flash)
                    self.is_step_flashing = True
                    self.timer = 0.45
                else:
                    # Fin de secuencia: turno del jugador
                    self.state = GameState.PLAYER_TURN
                    self.player_step = 0
                    self.current_hovered_panel = -1
                    self.hover_duration = 0.0
                    self.debounce_cooldown = 0.30
            else:
                self.is_step_flashing = False
                self.sequence_step += 1
                self.timer = 0.18

    def _update_player_turn(self, dt, pointer_active, pointer_pos):
        hovered = self.grid.get_panel_at(pointer_pos) if pointer_active else -1

        for i in range(9):
            if i == hovered:
                self.grid.set_panel_state(i, PanelState.HOVERED, duration=0.05)

        if hovered != -1 and self.debounce_cooldown <= 0.0:
            if hovered == self.current_hovered_panel:
                self.hover_duration += dt
                # ACTIVACIÓN TRAS 2 SEGUNDOS CONTINUOS CON EL DEDO EN EL PANEL
                if self.hover_duration >= self.required_dwell_time:
                    self._trigger_panel_press(hovered)
                    self.hover_duration = 0.0
                    self.debounce_cooldown = self.debounce_cooldown_time
            else:
                self.current_hovered_panel = hovered
                self.hover_duration = 0.0
        else:
            self.current_hovered_panel = -1
            self.hover_duration = 0.0

    def _trigger_panel_press(self, index):
        expected = self.full_sequence[self.player_step]

        if index == expected:
            # Acierto
            self.grid.set_panel_state(index, PanelState.PRESSED, duration=0.35)
            self.sound.play_panel_tone(index)
            self.player_step += 1

            if self.player_step >= self.current_round:
                self.state = GameState.ROUND_WON
                self.timer = 0.85
                self.grid.set_all_state(PanelState.SUCCESS, duration=0.60)
                self.sound.play_success_chime()
        else:
            # Fallo
            self.state = GameState.ROUND_FAILED
            self.timer = 1.0
            self.grid.set_all_state(PanelState.ERROR, duration=0.80)
            self.sound.play_error_buzzer()

    def draw(self, surface, pointer_active, pointer_pos):
        surface.fill((14, 18, 26))

        # Barra superior de navegación estilo consola
        pygame.draw.rect(surface, (20, 26, 38), (0, 0, self.screen_width, 55))
        pygame.draw.line(surface, (45, 60, 85), (0, 55), (self.screen_width, 55), 2)

        title_surf = self.font_large.render("REACTOR MEMORY", True, (160, 215, 255))
        surface.blit(title_surf, (25, 16))

        # Indicadores LED de las 5 rondas
        led_start_x = self.screen_width - 210
        for i in range(self.max_rounds):
            led_rect = pygame.Rect(led_start_x + i * 36, 18, 24, 16)
            if i < self.current_round - 1 or (self.state == GameState.ROUND_WON and i == self.current_round - 1):
                col = (50, 230, 120) # Verde superado
            elif i == self.current_round - 1 and self.state != GameState.VICTORY:
                col = (60, 180, 255) # Azul en curso
            else:
                col = (35, 45, 60)   # Apagado

            pygame.draw.rect(surface, col, led_rect, border_radius=3)
            pygame.draw.rect(surface, (80, 105, 135), led_rect, width=2, border_radius=3)

        # Dibujar cuadrícula con barra de llenado por dwell time
        charging_idx = self.current_hovered_panel if self.state == GameState.PLAYER_TURN else -1
        charging_prog = min(1.0, self.hover_duration / self.required_dwell_time)
        self.grid.draw(surface, charging_index=charging_idx, charging_progress=charging_prog)

        # Mensajes de estado
        status_text = ""
        status_col = (255, 255, 255)
        if self.state == GameState.START_SCREEN:
            status_text = "COLOCA EL DEDO SOBRE UN PANEL O PULSA ESPACIO"
            status_col = (180, 220, 255)
        elif self.state == GameState.SHOW_SEQUENCE:
            status_text = "MEMORIZA EL PATRON..."
            status_col = (255, 215, 0)
        elif self.state == GameState.PLAYER_TURN:
            if self.current_hovered_panel != -1 and self.hover_duration > 0.0:
                status_text = f"MANTEN EL DEDO: {self.hover_duration:.1f}s / {self.required_dwell_time:.1f}s"
                status_col = (255, 235, 80)
            else:
                status_text = "MANTEN EL DEDO 2 SEGUNDOS SOBRE CADA PANEL"
                status_col = (80, 235, 255)
        elif self.state == GameState.ROUND_WON:
            status_text = "CORRECTO!"
            status_col = (50, 240, 120)
        elif self.state == GameState.ROUND_FAILED:
            status_text = "FALLO EN EL REACTOR! REINTENTANDO..."
            status_col = (255, 60, 70)
        elif self.state == GameState.VICTORY:
            status_text = "REACTOR DESBLOQUEADO! PRESIONA ESPACIO"
            status_col = (50, 255, 140)

        msg_surf = self.font_med.render(status_text, True, status_col)
        surface.blit(msg_surf, ((self.screen_width - msg_surf.get_width()) // 2, self.screen_height - 48))

        # Miniatura de la cámara USB
        preview_surf = self.vision.get_preview_surface(self.preview_w, self.preview_h)
        border_rect = pygame.Rect(self.cam_x - 3, self.cam_y - 3, self.preview_w + 6, self.preview_h + 6)
        pygame.draw.rect(surface, (40, 55, 75), border_rect, border_radius=4)

        if preview_surf:
            surface.blit(preview_surf, (self.cam_x, self.cam_y))
        else:
            pygame.draw.rect(surface, (0, 0, 0), (self.cam_x, self.cam_y, self.preview_w, self.preview_h))

        # Estado de la cámara y tecla para alternar
        status_bar = pygame.Rect(self.cam_x, self.cam_y + self.preview_h - 20, self.preview_w, 20)
        s_surf = pygame.Surface((status_bar.width, status_bar.height), pygame.SRCALPHA)
        s_surf.fill((10, 15, 22, 210))
        surface.blit(s_surf, (status_bar.x, status_bar.y))

        cam_text = self.font_small.render(self.vision.get_camera_status(), True, (200, 255, 255))
        surface.blit(cam_text, (self.cam_x + 4, self.cam_y + self.preview_h - 17))

        c_hint = self.font_small.render("[C] Cambiar Cam", True, (255, 220, 100))
        surface.blit(c_hint, (self.cam_x + 4, self.cam_y + 4))

        # Dibujar cursor del dedo y anillo de progreso de los 2 segundos
        if pointer_active:
            px, py = pointer_pos
            pygame.draw.circle(surface, (0, 255, 220), (px, py), 14)
            pygame.draw.circle(surface, (255, 255, 255), (px, py), 18, width=2)

            if self.current_hovered_panel != -1 and self.hover_duration > 0.0:
                prog = min(1.0, self.hover_duration / self.required_dwell_time)
                # Anillo de progreso alrededor del dedo
                arc_rect = pygame.Rect(px - 26, py - 26, 52, 52)
                start_angle = -math.pi / 2
                stop_angle = start_angle + (2 * math.pi * prog)
                if stop_angle > start_angle:
                    pygame.draw.arc(surface, (255, 220, 40), arc_rect, -stop_angle, -start_angle, 4)

                rem_sec = max(0.0, self.required_dwell_time - self.hover_duration)
                rem_text = self.font_small.render(f"{rem_sec:.1f}s", True, (255, 240, 100))
                surface.blit(rem_text, (px + 22, py - 10))

    def cleanup(self):
        self.vision.stop()
