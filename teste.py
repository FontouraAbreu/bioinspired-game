# -*- coding: utf-8 -*-
"""
POC 2D de Plataforma Simples com Tiled Map e Inimigos Evolutivos.

ALGORITMO DE EVOLUÇÃO ATUALIZADO (SELEÇÃO ELITISTA):
A próxima geração de traços é baseada **APENAS** no inimigo com o
maior score de fitness (o "Elite") da geração atual.
Os novos traços são gerados através de Cruzamento (Crossover) e Mutação.
"""
import arcade
import random
import math

# --- Configurações do Jogo ---
# Restaurando as dimensões fixas da tela para simplificar a câmera
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
SCREEN_TITLE = "Plataforma com Evolução de Inimigos"

# Zoom da câmera: 2.0 significa que você verá metade do que via antes, ou seja, a câmera está 2x mais perto
CAMERA_ZOOM = 3.0

# Nome do arquivo de mapa Tiled
MAP_NAME = "assets/level-1.tmx"

# Constantes do Jogo
PLAYER_SCALE = 0.6  # Escala do jogador
ENEMY_SCALE = 0.3  # Escala do inimigo
PLAYER_MOVEMENT_SPEED = 5
PLAYER_JUMP_FORCE = 10
GRAVITY = 0.7

# --- CONSTANTES DE MOVIMENTO E TRAÇOS ---
ENEMY_MAX_RUN_SPEED = 4.0
ENEMY_PERCEPTION_RANGE = 400
ENEMY_ACCELERATION = 0.25
ENEMY_FRICTION = 0.95
ENEMY_DRIFT_DECELERATION = 0.6

MAX_TRAIT_VALUE = 5.0
MIN_TRAIT_VALUE = 1.0
TRAIT_MUTATION_RATE = 0.5
BEST_ENEMY_MUTATION_FACTOR = 0.1

# --- CONSTANTES DE FITNESS ---
PROXIMITY_SCORING_CONSTANT = 100.0
MIN_DISTANCE_EPSILON = 1.0
MIN_FITNESS_FOR_WEIGHTING = 0.01

# PESOS DE FITNESS
W_HITS = 1000.0
W_PROXIMITY = 1.0

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
BACKGROUND_COLOR = (173, 216, 230)


class Enemy(arcade.Sprite):
    """
    Classe base para os inimigos com traços evolutivos.
    Inclui rastreamento de fitness.
    """

    # Altera a escala padrão para a constante ENEMY_SCALE
    def __init__(self, traits: dict, image_path: str, scale: float = ENEMY_SCALE):

        # Cria um placeholder visual
        if image_path.startswith(":resources:") or image_path == "circle_placeholder":
            # O cálculo do raio deve ser ajustado para a nova escala do inimigo
            radius = int(20 * (scale / 0.4))
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
            self.traits.get("run", 1.0) / MAX_TRAIT_VALUE
        ) * ENEMY_MAX_RUN_SPEED
        self.max_fly_speed = self.traits.get("fly", 1.0) * TRAIT_MULTIPLIER
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

    def __init__(self, width=SCREEN_WIDTH, height=SCREEN_HEIGHT, title=SCREEN_TITLE):
        # Usamos as constantes fixas da tela
        super().__init__(width, height, title)

        self.player_list = None
        self.enemy_list = None
        self.enemy_physics_engines = []

        self.tile_map = None
        self.ground_list = None
        self.foreground_list = None
        self.player_sprite = None

        # Dimensões do mapa em pixels (calculadas no setup)
        self.map_width_pixels = 0
        self.map_height_pixels = 0
        self.tile_size = 16

        # Inicializa câmeras
        self.camera = arcade.camera.Camera2D()
        self.gui_camera = arcade.camera.Camera2D()

        # --- APLICA O ZOOM NO MUNDO DO JOGO ---
        self.camera.zoom = CAMERA_ZOOM

        self.physics_engine = None

        self.left_pressed = False
        self.right_pressed = False
        self.hit_cooldown = 0.0
        self.HIT_COOLDOWN_TIME = 1.0
        self.show_fitness_logs = True

        # --- NOVOS ESTADOS DE JOGO E CONTROLE ---
        self.game_state = "PLAYING"
        self.level = 1
        self.level_time = 0.0
        self.summary_data = None

        # Traços iniciais para a próxima geração
        self.next_generation_traits = [
            {"run": 5.0, "fly": 1.0, "jump": 5.0, "type": "running"},
            {"run": 1.0, "fly": 5.0, "jump": 1.0, "type": "flying"},
        ]

    def on_resize(self, width: float, height: float):
        """
        Chamado quando a janela é redimensionada.
        Ajusta as câmeras para o novo tamanho e reafirma o zoom.
        """
        super().on_resize(width, height)
        # Redimensiona as câmeras para o novo viewport
        # self.camera.resize(width, height)
        # self.gui_camera.resize(width, height)

        # Reaplicamos o zoom após redimensionar para manter a proximidade
        self.camera.zoom = CAMERA_ZOOM

    def setup(self):
        """Configura o mapa e o player (Chamado apenas uma vez no início)."""

        COLLISION_LAYER_NAME = "colission layer"
        FOREGROUND_LAYER_NAME = "Foreground"
        PLAYER_START_LAYER_NAME = "Player Start"

        layer_options = {
            COLLISION_LAYER_NAME: {
                "use_spatial_hash": True,
            }
        }

        # Define a cor de fundo
        arcade.set_background_color(BACKGROUND_COLOR)

        self.tile_map = arcade.load_tilemap(
            MAP_NAME, scaling=1.0, layer_options=layer_options
        )

        # 2. Calcula as dimensões do mapa em pixels
        self.map_width_pixels = self.tile_map.width * self.tile_map.tile_width
        self.map_height_pixels = self.tile_map.height * self.tile_map.tile_height
        self.tile_size = self.tile_map.tile_width

        # Configuração das listas e camadas
        self.player_list = arcade.SpriteList()
        self.enemy_list = arcade.SpriteList()
        self.enemy_physics_engines = []
        self.hit_cooldown = 0.0

        self.ground_list = self.tile_map.sprite_lists.get(COLLISION_LAYER_NAME)
        self.foreground_list = self.tile_map.sprite_lists.get(
            FOREGROUND_LAYER_NAME, arcade.SpriteList()
        )

        if self.ground_list is None:
            print(
                f"ATENÇÃO: A camada '{COLLISION_LAYER_NAME}' não foi encontrada. Usando SpriteList vazia."
            )
            self.ground_list = arcade.SpriteList()

        # Configuração do Player
        self.player_sprite = arcade.Sprite(
            ":resources:images/animated_characters/female_person/femalePerson_idle.png",
            PLAYER_SCALE,
        )
        self.player_sprite.width = self.tile_size * 0.8 * (PLAYER_SCALE / 0.4)
        self.player_sprite.height = self.tile_size * 0.8 * (PLAYER_SCALE / 0.4)

        # Ponto de Spawn do Player
        player_spawn_layer = self.tile_map.object_lists.get(PLAYER_START_LAYER_NAME)
        spawn_point_x, spawn_point_y = 50, 200  # Fallback

        if player_spawn_layer and player_spawn_layer[0]:
            try:
                spawn_point_x = player_spawn_layer[0].center_x
                spawn_point_y = player_spawn_layer[0].center_y
            except Exception as e:
                print(
                    f"Erro ao obter ponto de spawn do Player: {e}. Usando fallback ({spawn_point_x}, {spawn_point_y})."
                )
                pass

        self.player_sprite.center_x = spawn_point_x
        self.player_sprite.center_y = spawn_point_y
        self.player_list.append(self.player_sprite)

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

        # Centraliza a câmera no jogador instantaneamente no setup
        self.center_camera_to_player(instant=True)

    def setup_generation(self, traits_list):
        """Cria e posiciona a nova geração de inimigos com base em traits_list."""
        self.enemy_list = arcade.SpriteList()
        self.enemy_physics_engines = []
        self.level_time = 0.0
        self.game_state = "PLAYING"

        PLAYER_START_LAYER_NAME = "Player Start"
        player_spawn_layer = self.tile_map.object_lists.get(PLAYER_START_LAYER_NAME)
        spawn_point_x, spawn_point_y = 50, 200

        if player_spawn_layer and player_spawn_layer[0]:
            try:
                spawn_point_x = player_spawn_layer[0].center_x
                spawn_point_y = player_spawn_layer[0].center_y
            except Exception:
                pass

        self.player_sprite.center_x = spawn_point_x
        self.player_sprite.center_y = spawn_point_y
        self.player_sprite.change_x = 0
        self.player_sprite.change_y = 0

        for i, traits in enumerate(traits_list):
            enemy = Enemy(traits, "circle_placeholder", ENEMY_SCALE)
            enemy.set_target(self.player_sprite)

            spawn_x_offsets = [100, 250, 400]
            spawn_y_offsets = [0, 50, 100]

            offset_index = i % len(spawn_x_offsets)
            y_offset = spawn_y_offsets[i % len(spawn_y_offsets)] + self.tile_size * 0.5

            enemy.center_x = spawn_point_x + spawn_x_offsets[offset_index]
            enemy.center_y = spawn_point_y + y_offset

            self.enemy_list.append(enemy)

            if traits.get("type") != "flying":
                runner_engine = arcade.PhysicsEnginePlatformer(
                    enemy, gravity_constant=GRAVITY, walls=self.ground_list
                )
                self.enemy_physics_engines.append(runner_engine)
                enemy.set_physics_engine(runner_engine)

        # Centraliza a câmera no jogador após o spawn
        self.center_camera_to_player(instant=True)

    def _crossover_and_mutate(
        self, parent1_traits: dict, parent2_traits: dict, mutation_rate: float
    ) -> dict:
        """
        Implementa o Crossover Simples (One-Point) e aplica Mutação.
        """
        new_traits = {"type": parent1_traits["type"]}
        trait_keys = ["run", "fly", "jump"]

        crossover_point = random.randint(1, len(trait_keys) - 1)

        for i, key in enumerate(trait_keys):
            if i < crossover_point:
                base_value = parent1_traits.get(key, 1.0)
            else:
                base_value = parent2_traits.get(key, 1.0)

            mutation = random.uniform(-mutation_rate, mutation_rate)
            new_value = base_value + mutation

            new_value = max(MIN_TRAIT_VALUE, min(MAX_TRAIT_VALUE, new_value))

            new_traits[key] = new_value

        return new_traits

    def evolve_enemies(self):
        """
        Calcula os novos traços baseados no fitness da geração atual (Seleção Elitista).
        """

        old_traits_list = []
        fitness_scores = []

        if not self.enemy_list:
            return

        # 1. Calcular Fitness e Identificar o ELITE
        elite_enemy = self.enemy_list[0]
        max_fitness = -1.0

        for enemy in self.enemy_list:
            fitness = enemy.calculate_final_fitness()

            old_traits_list.append(enemy.traits.copy())
            fitness_scores.append(fitness)

            if fitness > max_fitness:
                max_fitness = fitness
                elite_enemy = enemy

        elite_traits = elite_enemy.traits.copy()
        print(f"Elite: {elite_traits['type']} com Fitness: {max_fitness:.2f}")

        # 2. Geração da Nova População (Seleção Elitista com Mutação Suave)
        new_traits_list_ordered = []
        elite_mutation_rate = TRAIT_MUTATION_RATE * BEST_ENEMY_MUTATION_FACTOR

        for i, old_enemy in enumerate(self.enemy_list):

            parent1_traits = elite_traits
            parent2_traits = old_enemy.traits.copy()
            enemy_type = old_enemy.traits["type"]

            if old_enemy is elite_enemy:
                # O Elite: Mutação Suave (taxa reduzida)
                child_traits = self._crossover_and_mutate(
                    parent1_traits,
                    parent1_traits,
                    elite_mutation_rate,
                )
            else:
                # Os Filhos: Crossover com o Elite + Mutação Normal
                child_traits = self._crossover_and_mutate(
                    parent1_traits,
                    parent2_traits,
                    TRAIT_MUTATION_RATE,
                )

            child_traits["type"] = enemy_type
            new_traits_list_ordered.append(child_traits)

        self.next_generation_traits = new_traits_list_ordered

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
                    "new_traits": self.next_generation_traits[i],
                    "is_elite": enemy is elite_enemy,
                }
            )

    def simulate_level_end(self):
        """Simula o fim do nível, executa a evolução e entra no estado de resumo."""
        self.evolve_enemies()
        self.level += 1
        self.game_state = "EVOLUTION_SUMMARY"

    def continue_to_next_generation(self):
        """Continua para o próximo nível após o resumo."""
        self.setup_generation(self.next_generation_traits)
        self.game_state = "PLAYING"
        self.level_time = 0.0
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

        elif key == arcade.key.G:
            self.show_fitness_logs = not self.show_fitness_logs

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

    def center_camera_to_player(self, instant=False):
        """
        Calcula a posição da câmera para centralizar o jogador e move a câmera.
        """
        # Posição do jogador no mundo
        screen_center_x = self.player_sprite.center_x - (self.camera.viewport_width / 2)
        screen_center_y = self.player_sprite.center_y - (
            self.camera.viewport_height / 2
        )

        # Se a posição central for negativa, corrige para 0 (não permite que a câmera saia do mapa na esquerda/baixo)
        if screen_center_x < 0:
            screen_center_x = 0
        if screen_center_y < 0:
            screen_center_y = 0

        # Limita a rolagem para que a borda direita/superior do mapa seja o limite
        if screen_center_x + self.camera.viewport_width > self.map_width_pixels:
            screen_center_x = self.map_width_pixels - self.camera.viewport_width
        if screen_center_y + self.camera.viewport_height > self.map_height_pixels:
            screen_center_y = self.map_height_pixels - self.camera.viewport_height

        # Garante que o screen_center_x/y nunca seja negativo após a limitação
        screen_center_x = max(0, screen_center_x)
        screen_center_y = max(0, screen_center_y)

        camera_center_position = (screen_center_x, screen_center_y)

        # Move a câmera instantaneamente para a nova posição (requerido pelo usuário)
        # O argumento instant=True não é usado aqui, mas manteremos o parâmetro
        # para referência futura se quisermos movimento suave.
        self.camera.position = self.player_sprite.position

    def on_update(self, delta_time):
        """Lógica de atualização a cada frame."""

        if self.game_state != "PLAYING":
            return

        self.level_time += delta_time

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

        # A CÂMERA DEVE SEGUIR O JOGADOR A CADA FRAME
        self.center_camera_to_player()

        # Se o player cair do mapa, reseta a geração (não evolui)
        if self.player_sprite.center_y < -100:
            print(
                f"Player caiu. Reiniciando Geração {self.level} com os mesmos traços."
            )
            self.setup_generation(self.next_generation_traits)
            self.hit_cooldown = 0.0

    def _get_trait_color(self, new_value, old_value):
        """Retorna a cor baseada na mudança de valor do traço (Melhorou=Verde, Piorou=Vermelho)."""
        TOLERANCE = 0.005
        if new_value > old_value + TOLERANCE:
            return arcade.color.GREEN
        elif new_value < old_value - TOLERANCE:
            return arcade.color.RED
        else:
            return arcade.color.WHITE

    def draw_evolution_summary(self):
        """Desenha a tela de resumo da evolução com layout melhorado."""

        # Usamos as dimensões fixas da tela para o GUI
        screen_width, screen_height = SCREEN_WIDTH, SCREEN_HEIGHT

        # ------------------- Fundo Semi-Transparente -------------------
        arcade.draw_lrbt_rectangle_filled(
            0,
            screen_width,
            0,
            screen_height,
            (0, 0, 0, 220),
        )

        center_x = screen_width / 2

        # ------------------- TÍTULOS E SUBTÍTULOS -------------------

        # Título
        arcade.draw_text(
            f"RESUMO DA EVOLUÇÃO - FIM DA GERAÇÃO {self.summary_data['level']}",
            center_x,
            screen_height - 60,
            arcade.color.YELLOW_ORANGE,
            28,
            anchor_x="center",
        )

        # Tempo de Nível
        arcade.draw_text(
            f"Tempo de Nível: {self.summary_data['time']:.2f} segundos",
            center_x,
            screen_height - 110,
            arcade.color.LIGHT_GRAY,
            16,
            anchor_x="center",
        )

        # ------------------- TABELA DE DADOS -------------------

        COL_X = {
            "ID": 80,
            "TIPO": 180,
            "FITNESS": 300,
            "HITS": 380,
            "PROXIMIDADE": 480,
            "TRAITS_START": 570,
        }

        START_Y = screen_height - 170
        LINE_HEIGHT = 20
        ROW_SPACING = LINE_HEIGHT * 3.5

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

        arcade.draw_text(
            "EVOLUÇÃO DOS TRAÇOS",
            COL_X["TRAITS_START"] + 100,
            START_Y,
            color_header,
            font_size_header,
            anchor_x="center",
        )

        START_Y -= LINE_HEIGHT * 1.5

        # Linhas de Dados
        for i, enemy_data in enumerate(self.summary_data["enemies"]):
            y = START_Y - (i * ROW_SPACING)

            # Linha Separadora
            arcade.draw_line(
                50,
                y + LINE_HEIGHT * 2,
                screen_width - 50,
                y + LINE_HEIGHT * 2,
                arcade.color.DARK_SLATE_GRAY,
                1,
            )

            # Colunas de Dados
            data_color = (
                arcade.color.YELLOW if enemy_data["is_elite"] else arcade.color.WHITE
            )

            arcade.draw_text(
                f"{enemy_data['id']}", COL_X["ID"], y, data_color, 14, anchor_x="center"
            )
            arcade.draw_text(
                enemy_data["type"].capitalize(),
                COL_X["TIPO"],
                y,
                data_color,
                14,
                anchor_x="center",
            )
            arcade.draw_text(
                f"{enemy_data['fitness']:.1f}",
                COL_X["FITNESS"],
                y,
                data_color,
                14,
                anchor_x="center",
            )
            arcade.draw_text(
                f"{enemy_data['hits']}",
                COL_X["HITS"],
                y,
                data_color,
                14,
                anchor_x="center",
            )
            arcade.draw_text(
                f"{enemy_data['proximity']:.1f}",
                COL_X["PROXIMIDADE"],
                y,
                data_color,
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

        # 1. Desenhar o MUNDO DO JOGO (mapa, player, inimigos) usando a CAMERA
        self.camera.use()

        if self.ground_list:
            self.ground_list.draw()

        if self.foreground_list:
            self.foreground_list.draw()

        self.player_list.draw()
        self.enemy_list.draw()

        # 2. Desenhar o HUD/GUI (texto, placar) usando a GUI_CAMERA para fixar na tela
        self.gui_camera.use()

        # Usamos as dimensões fixas da tela para o GUI
        screen_width, screen_height = SCREEN_WIDTH, SCREEN_HEIGHT

        # Desenha o número da Geração/Nível atual e tempo
        if self.game_state == "PLAYING":
            arcade.draw_text(
                f"Geração: {self.level} | Tempo: {self.level_time:.1f}s",
                screen_width - 250,
                screen_height - 20,
                arcade.color.DARK_BLUE,
                16,
                anchor_x="left",
            )

        # Desenha os logs de fitness ou a tela de resumo
        if self.game_state == "PLAYING" and self.show_fitness_logs:

            arcade.draw_text(
                "Pressione 'G' para esconder/mostrar logs. Pressione '0' para EVOLUIR.",
                10,
                screen_height - 20,
                arcade.color.GRAY,
                12,
            )

            y_offset = screen_height - 45

            for i, enemy in enumerate(self.enemy_list):
                temp_fitness = (W_HITS * enemy.hits) + (
                    W_PROXIMITY * enemy.proximity_score
                )
                text = f"E{i+1} ({enemy.traits['type'][0]}): F:{temp_fitness:.1f} | R:{enemy.traits['run']:.2f} | J:{enemy.traits['jump']:.2f} | Fl:{enemy.traits['fly']:.2f}"
                arcade.draw_text(
                    text,
                    10,
                    y_offset - (i * 20),
                    arcade.color.WHITE,
                    10,
                )

        if self.game_state == "EVOLUTION_SUMMARY":
            self.draw_evolution_summary()


if __name__ == "__main__":
    window = MyGame(SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_TITLE)
    window.setup()
    arcade.run()
