import pygame

class PanelState:
    IDLE = 0
    HOVERED = 1
    FLASHING = 2
    PRESSED = 3
    SUCCESS = 4
    ERROR = 5

class Panel:
    def __init__(self, index, rect):
        self.index = index
        self.rect = rect
        self.state = PanelState.IDLE
        self.timer = 0.0

class GridPanel:
    def __init__(self, area_rect, spacing=14):
        self.spacing = spacing
        self.panels = []

        cell_w = (area_rect.width - 2 * spacing) / 3.0
        cell_h = (area_rect.height - 2 * spacing) / 3.0

        for r in range(3):
            for c in range(3):
                idx = r * 3 + c
                rect = pygame.Rect(
                    area_rect.x + c * (cell_w + spacing),
                    area_rect.y + r * (cell_h + spacing),
                    cell_w,
                    cell_h
                )
                self.panels.append(Panel(idx, rect))

    def update(self, dt):
        for p in self.panels:
            if p.timer > 0.0:
                p.timer -= dt
                if p.timer <= 0.0:
                    p.timer = 0.0
                    p.state = PanelState.IDLE

    def set_panel_state(self, index, state, duration=0.35):
        if 0 <= index < len(self.panels):
            self.panels[index].state = state
            self.panels[index].timer = duration

    def set_all_state(self, state, duration=0.45):
        for p in self.panels:
            p.state = state
            p.timer = duration

    def get_panel_at(self, pos):
        for p in self.panels:
            if p.rect.collidepoint(pos):
                return p.index
        return -1

    def get_panel_rect(self, index):
        if 0 <= index < len(self.panels):
            return self.panels[index].rect
        return None

    def draw(self, surface, charging_index=-1, charging_progress=0.0):
        for p in self.panels:
            base_col, border_col = self._get_colors(p.state)

            # Fondo del panel con esquinas redondeadas
            pygame.draw.rect(surface, base_col, p.rect, border_radius=10)

            # Si este panel está cargando los 2 segundos de pulsación, dibujar llenado de energía
            if p.index == charging_index and charging_progress > 0.0:
                fill_h = p.rect.height * min(1.0, charging_progress)
                fill_rect = pygame.Rect(
                    p.rect.x + 4,
                    p.rect.bottom - fill_h - 4,
                    p.rect.width - 8,
                    fill_h
                )
                charge_surf = pygame.Surface((fill_rect.width, fill_rect.height), pygame.SRCALPHA)
                charge_surf.fill((0, 240, 255, 90))
                surface.blit(charge_surf, (fill_rect.x, fill_rect.y))
                border_col = (255, 235, 80)

            # Borde
            pygame.draw.rect(surface, border_col, p.rect, width=3, border_radius=10)

            # Centro brillante estilo consola reactor Among Us si está activo
            if p.state in (PanelState.FLASHING, PanelState.PRESSED):
                inner = p.rect.inflate(-p.rect.width * 0.4, -p.rect.height * 0.4)
                inner_surf = pygame.Surface((inner.width, inner.height), pygame.SRCALPHA)
                inner_surf.fill((230, 250, 255, 170))
                surface.blit(inner_surf, (inner.x, inner.y))

    def _get_colors(self, state):
        if state == PanelState.IDLE:
            return (24, 34, 52), (45, 65, 95)
        elif state == PanelState.HOVERED:
            return (40, 75, 110), (70, 140, 190)
        elif state in (PanelState.FLASHING, PanelState.PRESSED):
            return (60, 220, 255), (220, 250, 255)
        elif state == PanelState.SUCCESS:
            return (50, 230, 120), (140, 255, 180)
        elif state == PanelState.ERROR:
            return (235, 45, 60), (255, 120, 130)
        return (30, 30, 30), (80, 80, 80)
