import pygame
import sys
import random
import heapq
from collections import deque
import os

# ---------- Config ----------
FPS = 60
SCREEN_WIDTH = 900
SCREEN_HEIGHT = 700
TITLE = "Maze Runner - AJ Edition"
NUM_LEVELS = 50

DIFFICULTIES = {
    'Easy': {'scale': 1.0, 'time_mul': 1.2, 'hint': 3},
    'Normal': {'scale': 1.2, 'time_mul': 1.0, 'hint': 2},
    'Hard': {'scale': 1.5, 'time_mul': 0.8, 'hint': 1},
}

WHITE = (255,255,255)
BLACK = (0,0,0)
GRAY = (200,200,200)
YELLOW = (220,200,60)
BG = (12, 16, 22)

# controls: dr, dc (row, col)
MOVE_KEYS = {
    pygame.K_UP: (-1, 0), pygame.K_w: (-1, 0),
    pygame.K_DOWN: (1, 0), pygame.K_s: (1, 0),
    pygame.K_LEFT: (0, -1), pygame.K_a: (0, -1),
    pygame.K_RIGHT: (0, 1), pygame.K_d: (0, 1),
}

AJ_MESSAGES = [
    "AJ IS PROUD OF YOU!",
    "AJ IS IMPRESSED!",
    "AJ IS SHOCKED!",
    "AJ WILL GIVE YOU A COOKIE 🍪",
]

# ---------- Maze generation (DFS recursive backtracker) ----------
def generate_maze_cols_rows(level_idx, difficulty):
    base = 15
    add = level_idx // 5
    scale = DIFFICULTIES[difficulty]['scale']
    cols = int((base + add) * scale)
    rows = int((base + add) * scale * 0.8)
    cols = max(8, min(60, cols))
    rows = max(6, min(48, rows))
    return cols, rows

def dfs_maze(cols, rows, seed=None):
    random.seed(seed)
    visited = [[False]*cols for _ in range(rows)]
    walls = [[[True,True,True,True] for _ in range(cols)] for _ in range(rows)]
    def neighbors(r,c):
        res=[]
        if r>0: res.append((r-1,c,0))
        if c<cols-1: res.append((r,c+1,1))
        if r<rows-1: res.append((r+1,c,2))
        if c>0: res.append((r,c-1,3))
        return res
    stack=[(0,0)]
    visited[0][0]=True
    while stack:
        r,c = stack[-1]
        neigh = [(nr,nc,d) for (nr,nc,d) in neighbors(r,c) if not visited[nr][nc]]
        if neigh:
            nr,nc,d = random.choice(neigh)
            walls[r][c][d]=False
            opposite = (d+2)%4
            walls[nr][nc][opposite]=False
            visited[nr][nc]=True
            stack.append((nr,nc))
        else:
            stack.pop()
    return walls

# ---------- A* pathfinder (used for hint) ----------
def a_star(start, goal, walls, cols, rows):
    def neighbors(r,c):
        dirs = [(-1,0,0),(0,1,1),(1,0,2),(0,-1,3)]
        for dr,dc,d in dirs:
            nr, nc = r+dr, c+dc
            if 0<=nr<rows and 0<=nc<cols and not walls[r][c][d]:
                yield nr,nc
    sx, sy = start
    gx, gy = goal
    open_set = []
    heapq.heappush(open_set, (0, sx, sy))
    came_from = {}
    gscore = { (sx,sy): 0 }
    def h(a,b):
        return abs(a[0]-b[0]) + abs(a[1]-b[1])
    while open_set:
        _, r, c = heapq.heappop(open_set)
        if (r,c) == (gx,gy):
            path=[]
            cur=(r,c)
            while cur in came_from:
                path.append(cur)
                cur = came_from[cur]
            path.append((sx,sy))
            path.reverse()
            return path
        for nr,nc in neighbors(r,c):
            tentative = gscore[(r,c)] + 1
            if (nr,nc) not in gscore or tentative < gscore[(nr,nc)]:
                gscore[(nr,nc)] = tentative
                priority = tentative + h((nr,nc),(gx,gy))
                heapq.heappush(open_set, (priority, nr, nc))
                came_from[(nr,nc)] = (r,c)
    return None

# ---------- UI Button ----------
class Button:
    def __init__(self, rect, text, action=None, font=None, idx=None):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.action = action
        self.font = font
        self.idx = idx
    def draw(self, surf, selected=False):
        pygame.draw.rect(surf, (48,52,70), self.rect, border_radius=8)
        pygame.draw.rect(surf, WHITE, self.rect, 2, border_radius=8)
        txt = self.font.render(self.text, True, WHITE)
        surf.blit(txt, txt.get_rect(center=self.rect.center))
        if selected:
            arrow = self.font.render("▶", True, YELLOW)
            ar = arrow.get_rect()
            ar.centery = self.rect.centery
            ar.right = self.rect.left - 12
            surf.blit(arrow, ar)
    def handle_event(self, ev):
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            if self.rect.collidepoint(ev.pos) and self.action:
                self.action()

# ---------- Maze Level ----------
class MazeLevel:
    def __init__(self, idx, difficulty):
        self.idx = idx
        self.difficulty = difficulty
        self.cols, self.rows = generate_maze_cols_rows(idx, difficulty)
        seed = (idx+1) * 12345
        self.walls = dfs_maze(self.cols, self.rows, seed)
        self.start = (0,0)
        self.goal = (self.rows-1, self.cols-1)
        self.hint_path = None
        self.hint_used = 0
    def compute_hint(self, player_pos=None):
        st = player_pos if player_pos else self.start
        path = a_star(st, self.goal, self.walls, self.cols, self.rows)
        self.hint_path = path
        return path

# ---------- Main Game ----------
class MazeGame:
    def __init__(self):
        pygame.init()
        pygame.mixer.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption(TITLE)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont('Arial', 20)
        self.title_font = pygame.font.SysFont('Arial', 36, bold=True)
        self.running = True

        # Game state
        self.state = 'menu'  # menu, playing, level_select, instructions, pause, timeup, level_complete
        self.current_level_idx = 0
        self.difficulty = 'Normal'
        self.levels = [MazeLevel(i, self.difficulty) for i in range(NUM_LEVELS)]
        self.player_pos = [0,0]
        self.cell_w = 20
        self.cell_h = 20
        self.margin_x = 40
        self.margin_y = 100
        self.hints_left = DIFFICULTIES[self.difficulty]['hint']
        self.time_left = 0
        self.level_start_ticks = 0

        # selection indexes for menus
        self.selection_index = 0

        # buttons
        self.buttons = []
        self.create_menu_buttons()
        self.pause_buttons = []
        self.timeup_buttons = []
        self.levelcomplete_buttons = []

        # AJ message for current level complete
        self.aj_message = ""

        # try load celebration sound
        self.win_sound = None
        if os.path.isfile('win.wav'):
            try:
                self.win_sound = pygame.mixer.Sound('win.wav')
            except Exception:
                self.win_sound = None

    # ---------- menu / button creators ----------
    def create_menu_buttons(self):
        self.buttons = []
        bfont = pygame.font.SysFont('Arial', 24)
        w = 220; h = 52; sx = SCREEN_WIDTH//2 - w//2; sy = 200; spacing = 74
        labels = [('Play', self.start_play), ('Levels', self.open_level_select),
                  ('Difficulty', self.toggle_difficulty), ('Instructions', self.open_instructions),
                  ('Quit', self.quit_game)]
        for i,(lab,act) in enumerate(labels):
            self.buttons.append(Button((sx, sy + i*spacing, w, h), lab, action=act, font=bfont, idx=i))

    def start_play(self):
        self.state = 'playing'
        self.load_level(self.current_level_idx)

    def open_level_select(self):
        self.state = 'level_select'

    def toggle_difficulty(self):
        keys = list(DIFFICULTIES.keys())
        idx = keys.index(self.difficulty)
        idx = (idx + 1) % len(keys)
        self.difficulty = keys[idx]
        self.levels = [MazeLevel(i, self.difficulty) for i in range(NUM_LEVELS)]
        self.hints_left = DIFFICULTIES[self.difficulty]['hint']

    def open_instructions(self):
        self.state = 'instructions'

    def quit_game(self):
        self.running = False

    def load_level(self, idx):
        self.current_level_idx = idx
        self.current_level = self.levels[idx]
        self.player_pos = [self.current_level.start[0], self.current_level.start[1]]
        # compute tile sizes
        max_w = SCREEN_WIDTH - 2*self.margin_x
        max_h = SCREEN_HEIGHT - self.margin_y - 40
        self.cell_w = max(6, min(40, max_w // self.current_level.cols))
        self.cell_h = max(6, min(40, max_h // self.current_level.rows))
        total_w = self.cell_w * self.current_level.cols
        total_h = self.cell_h * self.current_level.rows
        self.margin_x = (SCREEN_WIDTH - total_w)//2
        self.margin_y = 100
        base_time = (self.current_level.cols * self.current_level.rows) // 6
        self.time_left = int(base_time * DIFFICULTIES[self.difficulty]['time_mul'])
        self.level_start_ticks = pygame.time.get_ticks()
        self.hints_left = DIFFICULTIES[self.difficulty]['hint']
        self.current_level.hint_used = 0
        self.current_level.hint_path = None
        self.selection_index = 0
        self.aj_message = random.choice(AJ_MESSAGES)

    # ---------- drawing ----------
    def draw_menu(self):
        self.screen.fill(BG)
        title = self.title_font.render(TITLE, True, WHITE)
        self.screen.blit(title, (SCREEN_WIDTH//2 - title.get_width()//2, 60))
        for btn in self.buttons:
            btn.draw(self.screen, selected=False)
        diff_txt = self.font.render(f"Difficulty: {self.difficulty}", True, WHITE)
        self.screen.blit(diff_txt, (SCREEN_WIDTH - diff_txt.get_width() - 20, 20))

    def draw_instructions(self):
        self.screen.fill(BG)
        lines = [
            "Instructions:",
            "- Use arrow keys or WASD to move from the green start to the red goal.",
            "- Press H for a hint (A* path) - limited uses per level.",
            "- Complete 50 levels. Mazes get larger and more complex.",
            "- Press ESC to pause during play.",
            "- Menus/buttons: Mouse OR Arrow keys + Enter."
        ]
        y = 80
        for i,l in enumerate(lines):
            f = self.title_font if i==0 else self.font
            surf = f.render(l, True, WHITE)
            self.screen.blit(surf, (40, y))
            y += 50 if i==0 else 34

    def draw_level_select(self):
        self.screen.fill(BG)
        title = self.title_font.render("Select Level", True, WHITE)
        self.screen.blit(title, (SCREEN_WIDTH//2 - title.get_width()//2, 20))
        cols_display = 10
        btn_w, btn_h, spacing = 70, 36, 10
        start_x = (SCREEN_WIDTH - (btn_w*cols_display + spacing*(cols_display-1)))//2
        y0 = 120
        for i in range(NUM_LEVELS):
            r = i // cols_display
            c = i % cols_display
            x = start_x + c*(btn_w + spacing)
            rect = pygame.Rect(x, y0 + r*(btn_h + spacing), btn_w, btn_h)
            color = (30,120,80) if i == self.current_level_idx else (40,40,80)
            pygame.draw.rect(self.screen, color, rect, border_radius=6)
            txt = self.font.render(str(i+1), True, WHITE)
            self.screen.blit(txt, txt.get_rect(center=rect.center))
        hint = self.font.render("Click a level to play. ESC to return to menu.", True, WHITE)
        self.screen.blit(hint, (20, SCREEN_HEIGHT-40))

    def draw_playing(self):
        self.screen.fill(BG)
        lvl = self.current_level
        # level background tint
        lvl_col = (50 + (lvl.idx*3)%200, 30 + (lvl.idx*5)%200, 60 + (lvl.idx*7)%180)
        pygame.draw.rect(self.screen, lvl_col, (0,0,SCREEN_WIDTH,SCREEN_HEIGHT))

        # draw maze cells & walls
        for r in range(lvl.rows):
            for c in range(lvl.cols):
                x = self.margin_x + c*self.cell_w
                y = self.margin_y + r*self.cell_h
                cell_rect = pygame.Rect(x,y,self.cell_w,self.cell_h)
                pygame.draw.rect(self.screen, (20,20,30), cell_rect)
                walls = lvl.walls[r][c]
                t = max(1, int(min(self.cell_w, self.cell_h)//6))
                if walls[0]: pygame.draw.line(self.screen, WHITE, (x,y),(x+self.cell_w,y), t)
                if walls[1]: pygame.draw.line(self.screen, WHITE, (x+self.cell_w,y),(x+self.cell_w,y+self.cell_h), t)
                if walls[2]: pygame.draw.line(self.screen, WHITE, (x,y+self.cell_h),(x+self.cell_w,y+self.cell_h), t)
                if walls[3]: pygame.draw.line(self.screen, WHITE, (x,y),(x,y+self.cell_h), t)

        # start & goal
        sx = self.margin_x + lvl.start[1]*self.cell_w
        sy = self.margin_y + lvl.start[0]*self.cell_h
        gx = self.margin_x + lvl.goal[1]*self.cell_w
        gy = self.margin_y + lvl.goal[0]*self.cell_h
        pygame.draw.rect(self.screen, (50,200,80), (sx+3, sy+3, self.cell_w-6, self.cell_h-6), border_radius=4)
        pygame.draw.rect(self.screen, (200,60,60), (gx+3, gy+3, self.cell_w-6, self.cell_h-6), border_radius=4)

        # hint path highlight (if present)
        if lvl.hint_path:
            for (pr,pc) in lvl.hint_path:
                hx = self.margin_x + pc*self.cell_w
                hy = self.margin_y + pr*self.cell_h
                inner = pygame.Rect(hx+int(self.cell_w*0.25), hy+int(self.cell_h*0.25), int(self.cell_w*0.5), int(self.cell_h*0.5))
                pygame.draw.rect(self.screen, (200,180,60), inner, border_radius=4)

        # player
        px = self.margin_x + self.player_pos[1]*self.cell_w
        py = self.margin_y + self.player_pos[0]*self.cell_h
        pygame.draw.circle(self.screen, (80,180,255), (px + self.cell_w//2, py + self.cell_h//2), max(6, min(self.cell_w, self.cell_h)//3))

        # HUD
        hud_y = 12
        self.screen.blit(self.font.render(f"Level {lvl.idx+1}/{NUM_LEVELS}", True, WHITE), (20,hud_y))
        self.screen.blit(self.font.render(f"Difficulty: {self.difficulty}", True, WHITE), (220,hud_y))
        self.screen.blit(self.font.render(f"Hints left: {self.hints_left}", True, WHITE), (420,hud_y))
        elapsed = (pygame.time.get_ticks() - self.level_start_ticks) // 1000
        tleft = max(0, self.time_left - elapsed)
        self.screen.blit(self.font.render(f"Time: {tleft}s", True, WHITE), (620,hud_y))

    def draw_pause(self):
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0,0,0,180))
        self.screen.blit(overlay, (0,0))
        msg = self.title_font.render("Paused", True, WHITE)
        self.screen.blit(msg, (SCREEN_WIDTH//2 - msg.get_width()//2, 120))
        if not self.pause_buttons:
            bfont = pygame.font.SysFont('Arial', 24)
            w = 280; h = 56; sx = SCREEN_WIDTH//2 - w//2
            self.pause_buttons = [
                Button((sx, 220, w, h), "Resume", action=self._action_resume, font=bfont, idx=0),
                Button((sx, 300, w, h), "Restart", action=self._action_restart, font=bfont, idx=1),
                Button((sx, 380, w, h), "Main Menu", action=self._action_mainmenu, font=bfont, idx=2),
            ]
        for i,btn in enumerate(self.pause_buttons):
            btn.draw(self.screen, selected=(i == self.selection_index))

    def draw_timeup(self):
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0,0,0,220))
        self.screen.blit(overlay, (0,0))
        msg = self.title_font.render("TIME'S UP! YOU ARE TOO SLOW", True, WHITE)
        self.screen.blit(msg, (SCREEN_WIDTH//2 - msg.get_width()//2, 140))
        if not self.timeup_buttons:
            bfont = pygame.font.SysFont('Arial', 24)
            w = 280; h = 56; sx = SCREEN_WIDTH//2 - w//2
            self.timeup_buttons = [
                Button((sx, 260, w, h), "Restart", action=self._action_restart, font=bfont, idx=0),
                Button((sx, 340, w, h), "Main Menu", action=self._action_mainmenu, font=bfont, idx=1),
            ]
        for i,btn in enumerate(self.timeup_buttons):
            btn.draw(self.screen, selected=(i == self.selection_index))

    def draw_level_complete(self):
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0,0,0,200))
        self.screen.blit(overlay, (0,0))
        msg = self.title_font.render("🎉 WOW! LEVEL COMPLETED 🎉", True, WHITE)
        self.screen.blit(msg, (SCREEN_WIDTH//2 - msg.get_width()//2, 110))
        sub = self.font.render(self.aj_message, True, YELLOW)
        self.screen.blit(sub, (SCREEN_WIDTH//2 - sub.get_width()//2, 170))
        if not self.levelcomplete_buttons:
            bfont = pygame.font.SysFont('Arial', 24)
            w = 280; h = 56; sx = SCREEN_WIDTH//2 - w//2
            self.levelcomplete_buttons = [
                Button((sx, 240, w, h), "Replay Level", action=self._action_restart, font=bfont, idx=0),
                Button((sx, 320, w, h), "Next Level", action=self._action_next_level, font=bfont, idx=1),
                Button((sx, 400, w, h), "Main Menu", action=self._action_mainmenu, font=bfont, idx=2),
            ]
        for i,btn in enumerate(self.levelcomplete_buttons):
            btn.draw(self.screen, selected=(i == self.selection_index))

    # ---------- actions ----------
    def _action_resume(self):
        self.state = 'playing'
        self.selection_index = 0

    def _action_restart(self):
        # replay current level
        self.load_level(self.current_level_idx)
        self.state = 'playing'
        self.selection_index = 0
        # clear popups
        self.levelcomplete_buttons = []
        self.timeup_buttons = []
        self.pause_buttons = []

    def _action_mainmenu(self):
        self.state = 'menu'
        self.selection_index = 0
        # clear popups
        self.levelcomplete_buttons = []
        self.timeup_buttons = []
        self.pause_buttons = []

    def _action_next_level(self):
        # proceed to next level
        if self.current_level_idx + 1 < NUM_LEVELS:
            self.load_level(self.current_level_idx + 1)
            self.state = 'playing'
        else:
            self.state = 'menu'
        self.selection_index = 0
        self.levelcomplete_buttons = []

    # ---------- event handling ----------
    def handle_events(self):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self.running = False
                return

            # GLOBAL debug shortcut
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_F1:
                self.state = 'menu'

            # MENU
            if self.state == 'menu':
                for b in self.buttons:
                    b.handle_event(ev)
                if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                    self.running = False

            # INSTRUCTIONS
            elif self.state == 'instructions':
                if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                    self.state = 'menu'
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    self.state = 'menu'

            # LEVEL SELECT
            elif self.state == 'level_select':
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    mx,my = ev.pos
                    cols_display = 10
                    btn_w, btn_h, spacing = 70, 36, 10
                    start_x = (SCREEN_WIDTH - (btn_w*cols_display + spacing*(cols_display-1)))//2
                    y0 = 120
                    for i in range(NUM_LEVELS):
                        r = i // cols_display
                        c = i % cols_display
                        x = start_x + c*(btn_w + spacing)
                        rect = pygame.Rect(x, y0 + r*(btn_h + spacing), btn_w, btn_h)
                        if rect.collidepoint((mx,my)):
                            self.load_level(i)
                            self.state = 'playing'
                            break
                if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                    self.state = 'menu'

            # PLAYING
            elif self.state == 'playing':
                if ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        self.state = 'pause'
                        self.selection_index = 0
                    elif ev.key == pygame.K_h:
                        if self.hints_left > 0:
                            player_cell = (self.player_pos[0], self.player_pos[1])
                            self.current_level.compute_hint(player_pos=player_cell)
                            self.hints_left -= 1
                            self.current_level.hint_used += 1
                    elif ev.key in MOVE_KEYS:
                        dr,dc = MOVE_KEYS[ev.key]
                        self.try_move(dr,dc)
                # clicking in playing area does nothing (but could be extended)

            # PAUSE
            elif self.state == 'pause':
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    for b in self.pause_buttons:
                        b.handle_event(ev)
                if ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        self.state = 'playing'
                    elif ev.key in (pygame.K_UP, pygame.K_w):
                        if self.pause_buttons:
                            self.selection_index = (self.selection_index - 1) % len(self.pause_buttons)
                    elif ev.key in (pygame.K_DOWN, pygame.K_s):
                        if self.pause_buttons:
                            self.selection_index = (self.selection_index + 1) % len(self.pause_buttons)
                    elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        idx = self.selection_index
                        if 0 <= idx < len(self.pause_buttons):
                            action = self.pause_buttons[idx].action
                            if action: action()

            # TIMEUP
            elif self.state == 'timeup':
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    for b in self.timeup_buttons:
                        b.handle_event(ev)
                if ev.type == pygame.KEYDOWN:
                    if ev.key in (pygame.K_UP, pygame.K_w):
                        if self.timeup_buttons:
                            self.selection_index = (self.selection_index - 1) % len(self.timeup_buttons)
                    elif ev.key in (pygame.K_DOWN, pygame.K_s):
                        if self.timeup_buttons:
                            self.selection_index = (self.selection_index + 1) % len(self.timeup_buttons)
                    elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        idx = self.selection_index
                        if 0 <= idx < len(self.timeup_buttons):
                            action = self.timeup_buttons[idx].action
                            if action: action()

            # LEVEL COMPLETE
            elif self.state == 'level_complete':
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    for b in self.levelcomplete_buttons:
                        b.handle_event(ev)
                if ev.type == pygame.KEYDOWN:
                    if ev.key in (pygame.K_UP, pygame.K_w):
                        if self.levelcomplete_buttons:
                            self.selection_index = (self.selection_index - 1) % len(self.levelcomplete_buttons)
                    elif ev.key in (pygame.K_DOWN, pygame.K_s):
                        if self.levelcomplete_buttons:
                            self.selection_index = (self.selection_index + 1) % len(self.levelcomplete_buttons)
                    elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        idx = self.selection_index
                        if 0 <= idx < len(self.levelcomplete_buttons):
                            action = self.levelcomplete_buttons[idx].action
                            if action: action()

    # ---------- movement logic ----------
    def try_move(self, dr, dc):
        r,c = self.player_pos
        nr, nc = r + dr, c + dc
        lvl = self.current_level
        if not (0 <= nr < lvl.rows and 0 <= nc < lvl.cols):
            return
        dir_map = {(-1,0):0, (0,1):1, (1,0):2, (0,-1):3}
        d = dir_map.get((dr,dc))
        if d is None: return
        if not lvl.walls[r][c][d]:
            self.player_pos = [nr, nc]
            # reached goal => show level complete popup (do NOT immediately auto-load)
            if (nr, nc) == lvl.goal:
                # play win sound if available
                if self.win_sound:
                    try:
                        self.win_sound.play()
                    except Exception:
                        pass
                self.state = 'level_complete'
                self.selection_index = 0
                self.levelcomplete_buttons = []
                # aj message already picked in load_level; ensure one exists
                if not self.aj_message:
                    self.aj_message = random.choice(AJ_MESSAGES)

    # ---------- update ----------
    def update(self):
        if self.state == 'playing':
            elapsed = (pygame.time.get_ticks() - self.level_start_ticks) // 1000
            if elapsed > self.time_left:
                # time up
                self.state = 'timeup'
                self.selection_index = 0
                self.timeup_buttons = []

    # ---------- main loop ----------
    def run(self):
        while self.running:
            self.handle_events()
            self.update()

            # draw current state
            if self.state == 'menu':
                self.draw_menu()
            elif self.state == 'instructions':
                self.draw_instructions()
            elif self.state == 'level_select':
                self.draw_level_select()
            elif self.state == 'playing':
                self.draw_playing()
            elif self.state == 'pause':
                self.draw_playing()
                self.draw_pause()
            elif self.state == 'timeup':
                self.draw_playing()
                self.draw_timeup()
            elif self.state == 'level_complete':
                self.draw_playing()
                self.draw_level_complete()

            pygame.display.flip()
            self.clock.tick(FPS)

        pygame.quit()
        sys.exit()

# ---------- run ----------
if __name__ == '__main__':
    game = MazeGame()
    game.run()
