# -*- coding: utf-8 -*-
"""
POC 2D de Plataforma Simples com Tiled Map e Inimigos Evolutivos.

NOVIDADE: Introdução de estados de jogo ('PLAYING', 'EVOLUTION_SUMMARY') para pausar
e exibir a tela de resumo da evolução ao final de cada geração (Tecla '0').

MELHORIA: Layout da tela de resumo da evolução foi reestruturado para melhor
visualização e espaçamento.
"""
import arcade
import random
import math

# --- Configurações do Jogo ---
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
SCREEN_TITLE = "Plataforma com Evolução de Inimigos"

# Nome do arquivo de mapa Tiled
MAP_NAME = "assets/test_level.tmx"

# Constantes do Jogo
PLAYER_MOVEMENT_SPEED = 5
PLAYER_JUMP_FORCE = 10
GRAVITY = 0.7

# --- CONSTANTES DE MOVIMENTO E TRAÇOS ---
ENEMY_MAX_RUN_SPEED = 4.0
ENEMY_PERCEPTION_RANGE = 400
ENEMY_ACCELERATION = 0.25
ENEMY_FRICTION = 0.95
ENEMY_DRIFT_DECELERATION = 0.6

MAX_TRAIT_VALUE = 5
MIN_TRAIT_VALUE = 1
TRAIT_MUTATION_RATE = 0.5  # A magnitude da mutação

# --- CONSTANTES DE FITNESS ---
PROXIMITY_SCORING_CONSTANT = 100.0
MIN_DISTANCE_EPSILON = 1.0

# Peso mínimo para um inimigo influenciar a evolução (evita divisão por zero)
MIN_FITNESS_FOR_WEIGHTING = 0.01

# PESOS DE FITNESS
W_HITS = 1000.0  # Peso para cada Hit (H)
W_PROXIMITY = 1.0  # Peso para a Pontuação de Proximidade (A)

# Limite de distância para considerar um "Hit"
HIT_SCORE_THRESHOLD = 20

# Constantes de Voo (Não Alteradas)
BAT_FLAP_LIFT = 8.0
BAT_GRAVITY_EFFECT = -0.3
HORIZONTAL_WOBBLE = 0.5
BAT_FLAP_BASE_INTERVAL = 0.5
BAT_FLAP_MIN_INTERVAL = 0.2
BAT_FLAP_MAX_INTERVAL = 1.2
BAT_FLAP_INTERVAL_ADJUSTMENT_FACTOR = 0.005
BAT_HEIGHT_DEAD_ZONE = 20
BAT_PROXIMITY_RANGE = 60
BAT_PROXIMITY_DEAD_ZONE_BONUS = 50
BAT_PROXIMITY_HORIZONTAL_DRAG = 0.7
TRAIT_MULTIPLIER = 0.5

# Configurações de Câmera e Cor
DEAD_ZONE_X = 150
BACKGROUND_COLOR = (173, 216, 230)


class Enemy(arcade.Sprite):
    """
    Classe base para os inimigos com traços evolutivos.
    Inclui rastreamento de fitness.
    """

    def __init__(self, traits: dict, image_path: str, scale: float = 0.4):

        # Cria um placeholder visual
        if image_path.startswith(":resources:") or image_path == "circle_placeholder":
            radius = int(20 * scale / 0.4)
            super().__init__(None, scale)
            self.texture = arcade.make_circle_texture(radius * 2, arcade.color.RED)
            self.width = radius * 2
            self.height = radius * 2

            # Ajusta a cor com base no traço 'run' para visualização
            run_norm = traits.get("run", 1) / MAX_TRAIT_VALUE
            color_intensity = int(255 * (1 - run_norm * 0.5))
            self.color = (255, color_intensity, color_intensity)
        else:
            super().__init__(image_path, scale)
            self.color = (255, 100, 100)

        self.traits = traits

        # Aplica traços
        self.max_run_speed = (
            self.traits.get("run", 1) / MAX_TRAIT_VALUE
        ) * ENEMY_MAX_RUN_SPEED
        self.max_fly_speed = self.traits.get("fly", 1) * TRAIT_MULTIPLIER
        self.flap_timer = random.uniform(0, BAT_FLAP_BASE_INTERVAL)

        self.physics_engine = None
        self.jump_cooldown = 0.0
        self.JUMP_COOLDOWN_TIME = 1.0
        self.is_drifting = False
        self.player_target = None

        # Variáveis de Rastreamento de Fitness
        self.hits = 0
        self.proximity_score = 0.0
        self.current_fitness = 0.0

    def calculate_final_fitness(self):
        """Calcula a pontuação de fitness final e armazena."""
        self.current_fitness = (W_HITS * self.hits) + (
            W_PROXIMITY * self.proximity_score
        )
        return self.current_fitness

    def set_target(self, player_sprite):
        self.player_target = player_sprite

    def set_physics_engine(self, engine):
        self.physics_engine = engine

    def update_movement(self, delta_time):
        """Lógica de movimento do inimigo. Detalhes omitidos por serem os mesmos da versão anterior."""
        if not self.player_target:
            return

        if self.jump_cooldown > 0:
            self.jump_cooldown -= delta_time

        # 1. Movimento Terrestre (run/jump)
        if self.traits.get("run", 0) > 0 and self.traits.get("type") != "flying":
            distance_to_player = self.player_target.center_x - self.center_x

            if abs(distance_to_player) > ENEMY_PERCEPTION_RANGE:
                self.change_x *= ENEMY_FRICTION
                self.is_drifting = False
                return

            desired_direction = 0
            if distance_to_player < 0:
                desired_direction = -1
            elif distance_to_player > 0:
                desired_direction = 1

            if desired_direction != 0:
                if (desired_direction * self.change_x < 0) and (
                    abs(self.change_x) > 0.5
                ):
                    self.is_drifting = True
                else:
                    self.is_drifting = False

            if self.is_drifting:
                self.change_x *= ENEMY_DRIFT_DECELERATION
                if abs(self.change_x) < 0.2:
                    self.is_drifting = False
                    self.change_x = 0
            elif desired_direction != 0:
                self.change_x += ENEMY_ACCELERATION * desired_direction
            else:
                self.change_x *= ENEMY_FRICTION

            self.change_x = max(
                min(self.change_x, self.max_run_speed), -self.max_run_speed
            )

            if self.traits.get("type") == "running":
                jump_trait = self.traits.get("jump", 0)
                if jump_trait > 0 and self.physics_engine and self.jump_cooldown <= 0:
                    player_higher = (
                        self.player_target.center_y > self.center_y + self.height * 0.5
                    )
                    player_close_x = (
                        abs(self.player_target.center_x - self.center_x) < 150
                    )
                    random_jump_chance = random.randint(1, 100) == 1

                    if (
                        (player_higher and player_close_x) or random_jump_chance
                    ) and self.physics_engine.can_jump():
                        jump_force = jump_trait / MAX_TRAIT_VALUE * PLAYER_JUMP_FORCE
                        self.change_y = jump_force
                        self.jump_cooldown = self.JUMP_COOLDOWN_TIME

        # 2. Movimento Vertical (fly)
        if self.traits.get("fly", 0) > 0 and self.traits.get("type") == "flying":
            self.change_y += BAT_GRAVITY_EFFECT

            dy = self.player_target.center_y - self.center_y
            dx = abs(self.player_target.center_x - self.center_x)

            vertical_dead_zone = BAT_HEIGHT_DEAD_ZONE
            if dx < BAT_PROXIMITY_RANGE:
                vertical_dead_zone += BAT_PROXIMITY_DEAD_ZONE_BONUS
                self.change_x *= BAT_PROXIMITY_HORIZONTAL_DRAG

            interval_adjustment = -dy * BAT_FLAP_INTERVAL_ADJUSTMENT_FACTOR
            current_interval = BAT_FLAP_BASE_INTERVAL + interval_adjustment
            current_interval = max(
                min(current_interval, BAT_FLAP_MAX_INTERVAL), BAT_FLAP_MIN_INTERVAL
            )

            self.flap_timer += delta_time
            if self.flap_timer >= current_interval:
                self.flap_timer = 0
                self.change_y = BAT_FLAP_LIFT

            target_direction = 0
            if self.player_target.center_x < self.center_x:
                target_direction = -1
            elif self.player_target.center_x > self.center_x:
                target_direction = 1

            wobble = random.uniform(-HORIZONTAL_WOBBLE, HORIZONTAL_WOBBLE)

            self.change_x += target_direction * self.max_fly_speed * delta_time
            self.change_x = max(
                min(self.change_x, self.max_fly_speed), -self.max_fly_speed
            )
            self.change_x += wobble * delta_time

            max_v_speed = self.traits.get("fly", 1) * TRAIT_MULTIPLIER * 1.5
            self.change_y = max(min(self.change_y, max_v_speed), -max_v_speed)


class MyGame(arcade.Window):
    """
    Classe Principal do Jogo - Gerencia o Player, Inimigos Evolutivos e Estados de Jogo.
    """

    def __init__(self, width, height, title):
        super().__init__(width, height, title)
        arcade.set_background_color(BACKGROUND_COLOR)

        self.player_list = None
        self.enemy_list = None
        self.enemy_physics_engines = []

        self.tile_map = None
        self.ground_list = None
        self.player_sprite = None
        self.map_width_pixels = 0
        self.tile_size = 32
        self.camera = arcade.camera.Camera2D()
        self.gui_camera = arcade.camera.Camera2D()
        self.physics_engine = None

        self.left_pressed = False
        self.right_pressed = False
        self.hit_cooldown = 0.0
        self.HIT_COOLDOWN_TIME = 1.0
        self.show_fitness_logs = True

        # --- NOVOS ESTADOS DE JOGO E CONTROLE ---
        self.game_state = "PLAYING"  # 'PLAYING' ou 'EVOLUTION_SUMMARY'
        self.level = 1
        self.level_time = 0.0  # Tempo que o nível está rodando
        self.summary_data = None  # Dados para a tela de resumo

        # Traços iniciais para a próxima geração
        self.next_generation_traits = [
            {"run": 5.0, "fly": 1.0, "jump": 5.0, "type": "running"},
            {"run": 1.0, "fly": 5.0, "jump": 1.0, "type": "flying"},
        ]

    def setup(self):
        """Configura o mapa e o player (Chamado apenas uma vez no início)."""
        self.player_list = arcade.SpriteList()
        self.enemy_list = arcade.SpriteList()
        self.enemy_physics_engines = []
        self.hit_cooldown = 0.0

        # Carregamento do Mapa
        layer_options = {
            "Tile Layer 1": {
                "use_spatial_hash": True,
            }
        }
        self.tile_map = arcade.load_tilemap(
            MAP_NAME, scaling=1.0, layer_options=layer_options
        )
        self.map_width_pixels = self.tile_map.width * self.tile_map.tile_width
        self.tile_size = self.tile_map.tile_width
        self.ground_list = self.tile_map.sprite_lists["Tile Layer 1"]

        # Configuração do Player
        self.player_sprite = arcade.Sprite(
            ":resources:images/animated_characters/female_person/femalePerson_idle.png",
            0.4,
        )
        self.player_sprite.width = self.tile_size * 0.8
        self.player_sprite.height = self.tile_size * 0.8

        player_spawn_layer = self.tile_map.object_lists.get("Player Start")
        spawn_point_x, spawn_point_y = 50, 200
        if player_spawn_layer and player_spawn_layer[0]:
            spawn_point_x = player_spawn_layer[0][0][0]
            spawn_point_y = player_spawn_layer[0][0][1]

        self.player_sprite.center_x = spawn_point_x
        self.player_sprite.center_y = spawn_point_y
        self.player_list.append(self.player_sprite)

        # Motor de Física do Player
        self.physics_engine = arcade.PhysicsEnginePlatformer(
            self.player_sprite, gravity_constant=GRAVITY, walls=self.ground_list
        )

        # Configuração da Geração Inicial de Inimigos
        self.setup_generation(self.next_generation_traits)

        # Estado inicial
        self.game_state = "PLAYING"
        self.level_time = 0.0
        self.left_pressed = False
        self.right_pressed = False
        self.camera.position = (self.player_sprite.center_x, 0)

    def setup_generation(self, traits_list):
        """Cria e posiciona a nova geração de inimigos com base em traits_list."""
        self.enemy_list = arcade.SpriteList()
        self.enemy_physics_engines = []
        self.level_time = 0.0  # Zera o tempo para a nova geração
        self.game_state = "PLAYING"  # Garante que o jogo está rodando

        player_spawn_layer = self.tile_map.object_lists.get("Player Start")
        spawn_point_x, spawn_point_y = 50, 200
        if player_spawn_layer and player_spawn_layer[0]:
            spawn_point_x = player_spawn_layer[0][0][0]
            spawn_point_y = player_spawn_layer[0][0][1]

        # Posições de spawn relativas ao player para manter a distância inicial
        spawn_x_offsets = [150, 300]
        spawn_y_offsets = [0, 100]

        self.player_sprite.center_x = spawn_point_x
        self.player_sprite.center_y = spawn_point_y
        self.player_sprite.change_x = 0
        self.player_sprite.change_y = 0

        for i, traits in enumerate(traits_list):
            enemy = Enemy(traits, "circle_placeholder", 0.4)
            enemy.set_target(self.player_sprite)

            # Reposiciona o inimigo
            enemy.center_x = spawn_point_x + spawn_x_offsets[i]
            enemy.center_y = spawn_point_y + spawn_y_offsets[i]

            self.enemy_list.append(enemy)

            # Inimigos terrestres precisam de motor de física de plataforma
            if traits.get("type") != "flying":
                runner_engine = arcade.PhysicsEnginePlatformer(
                    enemy, gravity_constant=GRAVITY, walls=self.ground_list
                )
                self.enemy_physics_engines.append(runner_engine)
                enemy.set_physics_engine(runner_engine)

    def evolve_enemies(self):
        """
        Calcula os novos traços baseados no fitness da geração atual (média ponderada + mutação).
        """
        total_fitness = 0.0
        weighted_sum_run = 0.0
        weighted_sum_fly = 0.0
        weighted_sum_jump = 0.0

        old_traits_list = []  # Armazena para o resumo
        fitness_scores = []  # Armazena para o resumo

        if not self.enemy_list:
            return

        # 1. Calcular o Fitness Final e a Soma Total
        for enemy in self.enemy_list:
            fitness = enemy.calculate_final_fitness()
            total_fitness += fitness

            old_traits_list.append(enemy.traits.copy())
            fitness_scores.append(fitness)

            # Garante peso mínimo para inimigos com 0 fitness
            weight = max(fitness, MIN_FITNESS_FOR_WEIGHTING)

            # Soma ponderada dos traços
            weighted_sum_run += enemy.traits["run"] * weight
            weighted_sum_fly += enemy.traits["fly"] * weight
            weighted_sum_jump += enemy.traits["jump"] * weight

        # Se o fitness total for muito baixo (evitar problemas de ponderação se todos tiverem ~0)
        if total_fitness < 0.1:
            total_fitness = len(self.enemy_list)
            # Recalcula as somas ponderadas com peso 1 (média simples)
            for enemy in self.enemy_list:
                weighted_sum_run += enemy.traits["run"] * 1
                weighted_sum_fly += enemy.traits["fly"] * 1
                weighted_sum_jump += enemy.traits["jump"] * 1

        new_traits_base = {
            "run": weighted_sum_run / total_fitness,
            "fly": weighted_sum_fly / total_fitness,
            "jump": weighted_sum_jump / total_fitness,
        }

        # 2. Criar a Nova Geração de Traços (Aplicando Mutação)
        new_traits_list = []
        for i, old_traits in enumerate(self.next_generation_traits):
            new_traits = {"type": old_traits["type"]}

            # Para cada traço, aplica o valor base ponderado + mutação aleatória
            for trait_key in ["run", "fly", "jump"]:

                mutation = random.uniform(-TRAIT_MUTATION_RATE, TRAIT_MUTATION_RATE)
                new_value = new_traits_base.get(trait_key, 1.0) + mutation

                # Fixa o valor entre MIN_TRAIT_VALUE e MAX_TRAIT_VALUE
                new_value = max(MIN_TRAIT_VALUE, min(MAX_TRAIT_VALUE, new_value))

                new_traits[trait_key] = new_value

            new_traits_list.append(new_traits)

        self.next_generation_traits = new_traits_list

        # 3. Armazenar dados do resumo
        self.summary_data = {
            "level": self.level,
            "time": self.level_time,
            "enemies": [],
        }

        for i, enemy in enumerate(self.enemy_list):
            self.summary_data["enemies"].append(
                {
                    "id": i + 1,
                    "type": enemy.traits["type"],
                    "fitness": fitness_scores[i],
                    "hits": enemy.hits,
                    "proximity": enemy.proximity_score,
                    "old_traits": old_traits_list[i],
                    "new_traits": new_traits_list[i],
                }
            )

    def simulate_level_end(self):
        """Simula o fim do nível, executa a evolução e entra no estado de resumo."""

        # 1. Executa a Evolução
        self.evolve_enemies()

        # 2. Incrementa o nível e muda o estado
        self.level += 1
        self.game_state = "EVOLUTION_SUMMARY"  # PAUSA O JOGO

    def continue_to_next_generation(self):
        """Continua para o próximo nível após o resumo."""
        self.setup_generation(self.next_generation_traits)
        self.game_state = "PLAYING"  # Reinicia o jogo
        self.level_time = 0.0  # Garante que o tempo está zerado
        self.summary_data = None
        self.hit_cooldown = 0.0

    def apply_movement(self):
        """Calcula a mudança de X do jogador com base nas teclas pressionadas."""
        self.player_sprite.change_x = 0

        if self.left_pressed and not self.right_pressed:
            self.player_sprite.change_x = -PLAYER_MOVEMENT_SPEED
        elif self.right_pressed and not self.left_pressed:
            self.player_sprite.change_x = PLAYER_MOVEMENT_SPEED

    def on_key_press(self, key, modifiers):
        """Atualiza o estado da tecla pressionada, recalcula o movimento e trata eventos de jogo."""

        if self.game_state == "EVOLUTION_SUMMARY":
            if key == arcade.key.ENTER:
                self.continue_to_next_generation()
            return

        if key == arcade.key.LEFT:
            self.left_pressed = True
        elif key == arcade.key.RIGHT:
            self.right_pressed = True
        elif key == arcade.key.UP or key == arcade.key.SPACE:
            if self.physics_engine.can_jump():
                self.player_sprite.change_y = PLAYER_JUMP_FORCE

        # Toggle do Log de Fitness com 'G'
        elif key == arcade.key.G:
            self.show_fitness_logs = not self.show_fitness_logs

        # Fim de Nível e Evolução com '0'
        elif key == arcade.key.KEY_0:
            self.simulate_level_end()

        self.apply_movement()

    def on_key_release(self, key, modifiers):
        """Atualiza o estado da tecla solta e recalcula o movimento."""
        if self.game_state != "PLAYING":
            return

        if key == arcade.key.LEFT:
            self.left_pressed = False
        elif key == arcade.key.RIGHT:
            self.right_pressed = False

        self.apply_movement()

    def center_camera_to_player(self):
        """Move a câmera suavemente."""
        current_camera_x = self.camera.position[0]
        camera_center_x = current_camera_x + SCREEN_WIDTH / 2
        screen_center_x = current_camera_x

        if self.player_sprite.center_x < camera_center_x - DEAD_ZONE_X:
            screen_center_x = (
                self.player_sprite.center_x + DEAD_ZONE_X - SCREEN_WIDTH / 2
            )
        elif self.player_sprite.center_x > camera_center_x + DEAD_ZONE_X:
            screen_center_x = (
                self.player_sprite.center_x - DEAD_ZONE_X - SCREEN_WIDTH / 2
            )

        screen_center_x = max(0, screen_center_x)
        max_scroll_x = self.map_width_pixels - SCREEN_WIDTH
        screen_center_x = min(max_scroll_x, screen_center_x)
        screen_center_y = 0

        player_centered = (round(screen_center_x), round(screen_center_y))
        self.camera.position = player_centered

    def on_update(self, delta_time):
        """Lógica de atualização a cada frame."""

        if self.game_state != "PLAYING":
            return

        self.level_time += delta_time  # Rastreia o tempo apenas se estiver jogando

        self.physics_engine.update()
        if self.hit_cooldown > 0:
            self.hit_cooldown -= delta_time

        # --- Lógica de Inimigos e Rastreamento de Fitness ---
        for enemy in self.enemy_list:
            enemy.update_movement(delta_time)

            if enemy.traits.get("type") == "flying":
                enemy.update()

            # RASTREAMENTO DE FITNESS
            dx = self.player_sprite.center_x - enemy.center_x
            dy = self.player_sprite.center_y - enemy.center_y
            distance = math.sqrt(dx**2 + dy**2)

            # Pontuação de Proximidade Cumulativa
            proximity_increment = (
                PROXIMITY_SCORING_CONSTANT / (distance + MIN_DISTANCE_EPSILON)
            ) * delta_time
            enemy.proximity_score += proximity_increment

            # Hits (Colisão simplificada)
            if distance < HIT_SCORE_THRESHOLD and self.hit_cooldown <= 0:
                enemy.hits += 1
                self.hit_cooldown = self.HIT_COOLDOWN_TIME

        for engine in self.enemy_physics_engines:
            engine.update()

        self.enemy_list.update()

        self.center_camera_to_player()

        self.camera.position = self.player_sprite.position

        # Se o player cair do mapa, reseta a geração (não evolui)
        if self.player_sprite.center_y < -100:
            print(
                f"Player caiu. Reiniciando Geração {self.level} com os mesmos traços."
            )
            self.setup_generation(self.next_generation_traits)
            self.hit_cooldown = 0.0

    def _get_trait_color(self, new_value, old_value):
        """Retorna a cor baseada na mudança de valor do traço (Melhorou=Verde, Piorou=Vermelho)."""
        # Define uma tolerância para evitar cores para pequenas flutuações de ponto flutuante
        TOLERANCE = 0.005

        if new_value > old_value + TOLERANCE:
            return arcade.color.GREEN
        elif new_value < old_value - TOLERANCE:
            return arcade.color.RED
        else:
            return arcade.color.WHITE

    def draw_evolution_summary(self):
        """Desenha a tela de resumo da evolução com layout melhorado."""

        # ------------------- Fundo Semi-Transparente (Cobre a tela inteira) -------------------
        arcade.draw_lrbt_rectangle_filled(
            0,
            SCREEN_WIDTH,
            0,
            SCREEN_HEIGHT,
            (0, 0, 0, 220),  # Preto com 85% de opacidade
        )

        center_x = SCREEN_WIDTH / 2

        # ------------------- TÍTULOS E SUBTÍTULOS -------------------

        # Título
        arcade.draw_text(
            f"RESUMO DA EVOLUÇÃO - FIM DA GERAÇÃO {self.summary_data['level']}",
            center_x,
            SCREEN_HEIGHT - 60,
            arcade.color.YELLOW_ORANGE,
            28,
            anchor_x="center",
        )

        # Tempo de Nível
        arcade.draw_text(
            f"Tempo de Nível: {self.summary_data['time']:.2f} segundos",
            center_x,
            SCREEN_HEIGHT - 110,
            arcade.color.LIGHT_GRAY,
            16,
            anchor_x="center",
        )

        # ------------------- TABELA DE DADOS -------------------

        # Posições X para cada coluna (coordenadas de tela otimizadas)
        COL_X = {
            "ID": 80,
            "TIPO": 180,
            "FITNESS": 300,
            "HITS": 380,
            "PROXIMIDADE": 480,
            "TRAITS_START": 570,  # Ponto de início para a lista de 3 traços (Left Anchor)
        }

        START_Y = SCREEN_HEIGHT - 170
        LINE_HEIGHT = 20  # Altura de cada linha de texto
        ROW_SPACING = (
            LINE_HEIGHT * 3.5
        )  # Espaçamento entre inimigos (inclui 3 linhas de traços + margem)

        # Cabeçalho da Tabela
        color_header = arcade.color.CYAN
        font_size_header = 14

        arcade.draw_text(
            "ID",
            COL_X["ID"],
            START_Y,
            color_header,
            font_size_header,
            anchor_x="center",
        )
        arcade.draw_text(
            "TIPO",
            COL_X["TIPO"],
            START_Y,
            color_header,
            font_size_header,
            anchor_x="center",
        )
        arcade.draw_text(
            "FITNESS (F)",
            COL_X["FITNESS"],
            START_Y,
            color_header,
            font_size_header,
            anchor_x="center",
        )
        arcade.draw_text(
            "HITS (H)",
            COL_X["HITS"],
            START_Y,
            color_header,
            font_size_header,
            anchor_x="center",
        )
        arcade.draw_text(
            "PROX. (P)",
            COL_X["PROXIMIDADE"],
            START_Y,
            color_header,
            font_size_header,
            anchor_x="center",
        )

        # O cabeçalho da coluna de Traços é centralizado sobre as três linhas de traço
        arcade.draw_text(
            "EVOLUÇÃO DOS TRAÇOS",
            COL_X["TRAITS_START"] + 100,
            START_Y,
            color_header,
            font_size_header,
            anchor_x="center",
        )

        START_Y -= LINE_HEIGHT * 1.5  # Espaço após o cabeçalho

        # Linhas de Dados
        for i, enemy_data in enumerate(self.summary_data["enemies"]):
            y = START_Y - (i * ROW_SPACING)

            # Linha Separadora
            arcade.draw_line(
                50,
                y + LINE_HEIGHT * 2,  # Posição superior da linha
                SCREEN_WIDTH - 50,
                y + LINE_HEIGHT * 2,
                arcade.color.DARK_SLATE_GRAY,
                1,
            )

            # Colunas de Dados
            arcade.draw_text(
                f"{enemy_data['id']}",
                COL_X["ID"],
                y,
                arcade.color.WHITE,
                14,
                anchor_x="center",
            )
            arcade.draw_text(
                enemy_data["type"].capitalize(),
                COL_X["TIPO"],
                y,
                arcade.color.WHITE,
                14,
                anchor_x="center",
            )
            arcade.draw_text(
                f"{enemy_data['fitness']:.1f}",
                COL_X["FITNESS"],
                y,
                arcade.color.YELLOW,
                14,
                anchor_x="center",
            )
            arcade.draw_text(
                f"{enemy_data['hits']}",
                COL_X["HITS"],
                y,
                arcade.color.WHITE,
                14,
                anchor_x="center",
            )
            arcade.draw_text(
                f"{enemy_data['proximity']:.1f}",
                COL_X["PROXIMIDADE"],
                y,
                arcade.color.WHITE,
                14,
                anchor_x="center",
            )

            # Coluna de Traços (Três linhas)
            old = enemy_data["old_traits"]
            new = enemy_data["new_traits"]

            # 1. RUN Trait
            color_run = self._get_trait_color(new["run"], old["run"])
            trait_text_run = f"RUN: {old['run']:.2f} -> {new['run']:.2f}"
            arcade.draw_text(
                trait_text_run,
                COL_X["TRAITS_START"],
                y + LINE_HEIGHT,
                color_run,
                12,
                anchor_x="left",
            )

            # 2. FLY Trait
            color_fly = self._get_trait_color(new["fly"], old["fly"])
            trait_text_fly = f"FLY: {old['fly']:.2f} -> {new['fly']:.2f}"
            arcade.draw_text(
                trait_text_fly, COL_X["TRAITS_START"], y, color_fly, 12, anchor_x="left"
            )

            # 3. JUMP Trait
            color_jump = self._get_trait_color(new["jump"], old["jump"])
            trait_text_jump = f"JUMP: {old['jump']:.2f} -> {new['jump']:.2f}"
            arcade.draw_text(
                trait_text_jump,
                COL_X["TRAITS_START"],
                y - LINE_HEIGHT,
                color_jump,
                12,
                anchor_x="left",
            )

        # ------------------- INSTRUÇÃO DE CONTINUIDADE -------------------

        arcade.draw_text(
            "Pressione [ENTER] para iniciar a Próxima Geração.",
            center_x,
            50,
            arcade.color.YELLOW_ORANGE,
            22,
            anchor_x="center",
        )

    def on_draw(self):
        """Renderiza a tela."""
        self.clear()

        self.camera.use()
        if self.ground_list:
            self.ground_list.draw()
        self.player_list.draw()
        self.enemy_list.draw()

        self.gui_camera.use()

        # Desenha o número da Geração/Nível atual e tempo
        if self.game_state == "PLAYING":
            arcade.draw_text(
                f"Geração: {self.level} | Tempo: {self.level_time:.1f}s",
                SCREEN_WIDTH - 250,
                SCREEN_HEIGHT - 20,
                arcade.color.DARK_BLUE,
                16,
                anchor_x="left",
            )

        # Desenha os logs de fitness ou a tela de resumo
        if self.game_state == "PLAYING" and self.show_fitness_logs:

            arcade.draw_text(
                "Pressione 'G' para esconder/mostrar logs. Pressione '0' para EVOLUIR.",
                10,
                SCREEN_HEIGHT - 20,
                arcade.color.GRAY,
                12,
            )

            y_offset = SCREEN_HEIGHT - 45

            for i, enemy in enumerate(self.enemy_list):
                fitness_score = (W_HITS * enemy.hits) + (
                    W_PROXIMITY * enemy.proximity_score
                )
                traits_str = f"R:{enemy.traits['run']:.2f} | F:{enemy.traits['fly']:.2f} | J:{enemy.traits['jump']:.2f}"

                text = f"E{i+1} ({enemy.traits.get('type')}): F={fitness_score:.1f} | Hits={enemy.hits} | {traits_str}"

                arcade.draw_text(
                    text,
                    10,
                    y_offset - (i * 20),
                    arcade.color.BLACK,
                    14,
                )

        elif self.game_state == "EVOLUTION_SUMMARY":
            # Usa a função de desenho melhorada
            self.draw_evolution_summary()  # Desenha a nova tela de resumo


def main():
    """Função principal para rodar o jogo."""
    window = MyGame(SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_TITLE)
    window.setup()
    arcade.run()


if __name__ == "__main__":
    main()
