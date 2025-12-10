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
import xml.etree.ElementTree as ET
import os

# --- Configurações do Jogo ---
# Restaurando as dimensões fixas da tela para simplificar a câmera
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
SCREEN_TITLE = "Plataforma com Evolução de Inimigos"

PARALLAX_LAYERS = {
    "bg 0": 0.0,  # Fundo mais distante (quase não se move)
    "bg 1": 0.2,  # Fundo médio (move-se um pouco)
    "bg 2": 0.5,  # Fundo mais próximo (move-se bastante)
}

# Zoom da câmera: 2.0 significa que você verá metade do que via antes, ou seja, a câmera está 2x mais perto
CAMERA_ZOOM = 2.0

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

# --- CONSTANTES DE NADO (SWIMMER) ---
SWIM_TILE_ID = 59  # ID do tile de água no Tiled Map (AJUSTADO PARA 59)
SWIM_BASE_SPEED = 1.0  # Velocidade de perseguição lenta na água
SWIMMER_ATTACK_RANGE = 100  # Raio para ativar o pulo de ataque
SWIMMER_JUMP_FORCE = 15.0  # Força do pulo de ataque
SWIMMER_ATTACK_COOLDOWN = (
    2.0  # Tempo de recarga do ataque (para não pular infinitamente)
)
SWIM_VERTICAL_BOOST = (
    0.5  # Para simular um movimento vertical lento (APENAS PARA AJUSTE)
)


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
BACKGROUND_COLOR = (46, 90, 137)

# --- MAPA DE SPRITES NATIVOS DO ARCADE ---
ENEMY_SPRITES_MAP = {
    "flying": ":resources:images/enemies/bee.png",
    "running": ":resources:images/enemies/frog.png",
    "swimming": ":resources:images/enemies/fishPink.png",
}

# --- FIM DO MAPA DE SPRITES ---


class BackgroundImage(arcade.Sprite):
    """Sprite simples para imagens de fundo estáticas."""

    def __init__(self, image_path, x, y):
        try:
            super().__init__(image_path, scale=1.0)
            self.center_x = x
            self.center_y = y
        except Exception as e:
            print(f"Erro ao carregar imagem {image_path}: {e}")


def load_background_images(tmx_path, map_width):
    """
    Carrega as imagens de fundo do arquivo .tmx e as repete horizontalmente.

    Args:
        tmx_path: Caminho do arquivo .tmx
        map_width: Largura total do mapa em pixels

    Retorna:
        Uma SpriteList com as imagens de fundo repetidas.
    """
    backgrounds = arcade.SpriteList()

    try:
        tree = ET.parse(tmx_path)
        root = tree.getroot()
        tmx_dir = os.path.dirname(tmx_path)

        for imagelayer in root.findall("imagelayer"):
            layer_name = imagelayer.get("name", "unknown")
            offsetx = int(imagelayer.get("offsetx", 0))
            offsety = int(imagelayer.get("offsety", 0))

            image_tag = imagelayer.find("image")
            if image_tag is not None:
                image_source = image_tag.get("source", "")
                image_width = int(image_tag.get("width", 0))
                image_height = int(image_tag.get("height", 0))
                image_path = os.path.join(tmx_dir, image_source)

                # Para cobrir corretamente mesmo que offsetx seja negativo,
                # começamos um pouco à esquerda do offset, garantindo cobertura
                # desde além da borda esquerda até além da largura do mapa.
                start_x = offsetx
                # Move start_x para a esquerda até ficar <= -image_width
                while start_x > -image_width:
                    start_x -= image_width

                end_x = map_width + image_width

                x = start_x
                while x < end_x:
                    center_x = x + image_width / 2
                    center_y = offsety + image_height / 2

                    bg_sprite = BackgroundImage(image_path, center_x, center_y)
                    backgrounds.append(bg_sprite)

                    x += image_width

                print(f"✓ Fundo repetido considerando offset: {layer_name}")
    except Exception as e:
        print(f"Erro ao carregar imagens de fundo: {e}")

    return backgrounds


# NOVO CAMINHO DO SPRITE DO PLAYER
PLAYER_IDLE_SPRITE = (
    ":resources:images/animated_characters/female_person/femalePerson_idle.png"
)

# --- FIM DO MAPA DE SPRITES ---


class Enemy(arcade.Sprite):
    """
    Classe base para os inimigos com traços evolutivos.
    Inclui rastreamento de fitness.
    """

    # Altera a escala padrão para a constante ENEMY_SCALE
    def __init__(self, traits: dict, scale: float = ENEMY_SCALE):

        enemy_type = traits.get("type")

        # 1. Escolhe o caminho da imagem com base no tipo de inimigo (usando o novo mapa)
        selected_image_path = ENEMY_SPRITES_MAP.get(enemy_type)

        # 2. Se o caminho for encontrado, carrega o sprite real
        if selected_image_path:
            super().__init__(selected_image_path, scale)
            self.color = (
                arcade.color.WHITE
            )  # Define a cor como branca para não interferir no sprite

        # 3. Fallback (se por algum motivo o tipo não estiver no mapa, usa o círculo placeholder original)
        else:
            print(
                f"AVISO: Tipo de inimigo '{enemy_type}' desconhecido. Usando placeholder."
            )
            radius = int(20 * (scale / 0.4))
            super().__init__(None, scale)
            self.texture = arcade.make_circle_texture(radius * 2, arcade.color.RED)
            self.width = radius * 2
            self.height = radius * 2

            # Ajusta a cor do placeholder com base no traço 'run' para visualização
            run_norm = traits.get("run", 1) / MAX_TRAIT_VALUE
            color_intensity = int(255 * (1 - run_norm * 0.5))
            self.color = (255, color_intensity, color_intensity)

        self.traits = traits

        # Aplica traços
        self.max_run_speed = (
            self.traits.get("run", 1.0) / MAX_TRAIT_VALUE
        ) * ENEMY_MAX_RUN_SPEED
        self.max_fly_speed = self.traits.get("fly", 1.0) * TRAIT_MULTIPLIER
        self.flap_timer = random.uniform(0, BAT_FLAP_BASE_INTERVAL)

        self.physics_engine = None
        self.ground_list = None  # Armazena a lista de colisões
        self.swim_tile_id = -1  # Armazena o ID do tile de nado

        self.jump_cooldown = 0.0
        self.JUMP_COOLDOWN_TIME = 1.0
        self.is_drifting = False
        self.player_target = None

        # Variável específica para o ataque de nado
        self.attack_cooldown = 0.0

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

    def set_physics_engine(self, engine, ground_list=None, swim_tile_id=None):
        """Define o motor de física e, se aplicável, informações de colisão/nado."""
        self.physics_engine = engine
        self.ground_list = ground_list
        if swim_tile_id is not None:
            self.swim_tile_id = swim_tile_id

    def is_on_swim_tile(self):
        """Verifica se o inimigo está sobre um tile de nado (ID 59)."""
        if not self.ground_list or self.swim_tile_id == -1:
            return False

        # Verifica colisão com qualquer tile do ground_list
        hit_list = arcade.check_for_collision_with_list(self, self.ground_list)

        for sprite in hit_list:
            tile_id = sprite.properties.get("tile_id")
            if tile_id == self.swim_tile_id:
                return True
        return False

    def is_swimming_collision(self, dx: float, dy: float) -> bool:
        """
        Verifica se o movimento proposto (dx, dy) colide com um tile
        que NÃO é o tile de nado (ID 59) E SE A COLISÃO ESTÁ NO NÍVEL DA ÁGUA.
        Se a colisão for muito acima do inimigo, ela é ignorada para permitir
        que ele nade por baixo de plataformas.
        Retorna True se houver colisão com um tile "não-navegável" no nível da água.
        """
        if not self.ground_list or self.swim_tile_id == -1:
            return False

        # 1. Pré-verificação de posição
        original_x = self.center_x
        original_y = self.center_y
        self.center_x += dx
        self.center_y += dy

        # 2. Verifica colisões com TODOS os tiles no ground_list
        hit_list = arcade.check_for_collision_with_list(self, self.ground_list)

        # 3. Retorna o sprite para a posição original
        self.center_x = original_x
        self.center_y = original_y

        # 4. Analisa as colisões
        if not hit_list:
            return False

        for sprite in hit_list:
            tile_id = sprite.properties.get("tile_id")

            # Se colidir com o tile de água, não bloqueia.
            if tile_id == self.swim_tile_id:
                continue

            # --- VERIFICAÇÃO DE NÍVEL DE COLISÃO ---
            # Se colidir com um tile NÃO-ÁGUA, verifica se este tile está
            # no nível horizontal do inimigo (ou ligeiramente acima/abaixo)
            # para ignorar plataformas muito altas.
            # Usaremos o centro do tile para checagem vertical.

            # Se a colisão ocorrer no eixo Y do inimigo, bloqueia.
            # Um limite de tolerância é usado (ex: 1.5x a altura do inimigo)
            vertical_tolerance = self.height * 1.5

            is_blocking_vertically = (
                abs(sprite.center_y - self.center_y) < vertical_tolerance
            )

            if is_blocking_vertically:
                # Colisão com um tile sólido no nível da água (parede/fundo)
                return True

        # Todas as colisões foram com tiles de água ou tiles sólidos muito altos (ignorados)
        return False

    def update_movement(self, delta_time):
        """Lógica de movimento do inimigo."""
        if not self.player_target:
            return

        if self.jump_cooldown > 0:
            self.jump_cooldown -= delta_time

        # Atualiza o cooldown de ataque do nadador
        if self.attack_cooldown > 0:
            self.attack_cooldown -= delta_time

        is_runner = self.traits.get("type") == "running"
        is_swimmer = self.traits.get("type") == "swimming"
        is_flying = self.traits.get("type") == "flying"

        # 1. Movimento Terrestre (run/jump) OU Nado
        if self.traits.get("run", 0) > 0 and (is_runner or is_swimmer):

            # Cálculo de distância
            dx = self.player_target.center_x - self.center_x
            dy = self.player_target.center_y - self.center_y
            distance = math.sqrt(dx**2 + dy**2)

            if abs(dx) > ENEMY_PERCEPTION_RANGE:
                self.change_x *= ENEMY_FRICTION
                self.is_drifting = False
                return

            desired_direction = 0
            if dx < 0:
                desired_direction = -1
            elif dx > 0:
                desired_direction = 1

            # --- Lógica de Nado (Swimmer) ---
            if is_swimmer:
                on_swim_tile = self.is_on_swim_tile()

                # Se o nadador não está na água, ele simplesmente para.
                if not on_swim_tile:
                    self.change_x = 0
                    self.change_y = 0
                    # Tenta se mover para baixo para encontrar a água se estiver no ar (pequeno ajuste)
                    self.center_y -= 0.5
                    return

                # Inimigo está na água:

                # --- SWIMMER_ATTACK_LOGIC: ATAQUE DE SALTO ---
                if distance < SWIMMER_ATTACK_RANGE and self.attack_cooldown <= 0:

                    # 1. Zera a velocidade horizontal para carregar o pulo
                    self.change_x = 0

                    # 2. Aplica o pulo (ataque)
                    # A força do pulo pode ser multiplicada pelo traço 'jump' do inimigo
                    jump_trait_factor = self.traits.get("jump", 1.0) / MAX_TRAIT_VALUE
                    jump_force = SWIMMER_JUMP_FORCE * jump_trait_factor

                    self.change_y = jump_force

                    # 3. Aplica cooldown
                    self.attack_cooldown = SWIMMER_ATTACK_COOLDOWN

                    # Adiciona um pequeno impulso horizontal na direção do player
                    self.change_x = desired_direction * 2

                    return  # Não faz mais nada, está no meio do pulo

                # --- SWIMMER_ATTACK_LOGIC: PERSEGUIÇÃO LENTA (Padrão) ---

                # 1. Movimento Horizontal Lento (Perseguição)

                # Multiplica a velocidade base pelo traço 'run' para evoluir a velocidade de perseguição
                current_swim_speed = SWIM_BASE_SPEED * (
                    self.traits.get("run", 1.0) / MAX_TRAIT_VALUE
                )

                self.change_x = desired_direction * current_swim_speed

                # Verifica colisão horizontal
                if self.is_swimming_collision(self.change_x, 0):
                    self.change_x = 0

                # 2. Movimento Vertical (Ajuste lento para manter na altura do player)
                # Mantém o centro do inimigo na vertical do player (ou apenas flutuando)
                if abs(dy) > self.height * 0.1:  # Margem para evitar oscilação
                    self.change_y = math.copysign(SWIM_VERTICAL_BOOST, dy)
                else:
                    self.change_y = 0

                # Verifica colisão vertical (com o fundo/topo)
                if self.is_swimming_collision(0, self.change_y):
                    self.change_y = 0

                # Nadadores não usam motor de plataforma.
                return

            # --- Lógica de Corrida e Salto (Apenas para "running") ---
            if is_runner:

                # Lógica de aceleração, fricção, e desvio (Drift)
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

                # Lógica de Salto
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
        if is_flying and self.traits.get("fly", 0) > 0:
            self.change_y += BAT_GRAVITY_EFFECT

            dx = self.player_target.center_x - self.center_x
            dy = self.player_target.center_y - self.center_y

            abs_dx = abs(dx)

            vertical_dead_zone = BAT_HEIGHT_DEAD_ZONE
            if abs_dx < BAT_PROXIMITY_RANGE:
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
            if dx < 0:
                target_direction = -1
            elif dx > 0:
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
        # Usamos as dimensões fixas da tela para o GUI
        super().__init__(width, height, title)

        self.player_list = None
        self.enemy_list = None
        self.enemy_physics_engines = []

        self.tile_map = None
        self.ground_list = None
        self.foreground_list = None
        self.player_sprite = None
        self.background_layers = {}
        self.background_images = []  # Lista para armazenar as imagens de fundo

        # Dimensões do mapa em pixels (calculadas no setup)
        self.map_width_pixels = 0
        self.map_height_pixels = 0
        self.tile_size = 16

        # Armazena a lista de posições dos tiles de água para o spawn
        self.water_tile_centers = []

        # Inicializa câmeras
        screen_limits = (width, height)
        screen_rect = arcade.LRBT(0, width, 0, height)
        self.camera = arcade.camera.Camera2D(viewport=screen_rect)
        self.gui_camera = arcade.camera.Camera2D(viewport=screen_rect)

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

        # Traços iniciais para a próxima geração (AGORA INCLUINDO O NADADOR)
        self.next_generation_traits = [
            {"run": 5.0, "fly": 1.0, "jump": 5.0, "type": "running"},
            {"run": 1.0, "fly": 5.0, "jump": 1.0, "type": "flying"},
            {"run": 3.0, "fly": 1.0, "jump": 1.0, "type": "swimming"},
        ]

    def on_resize(self, width: float, height: float):
        """
        Chamado quando a janela é redimensionada.
        Ajusta as câmeras para o novo tamanho e reafirma o zoom.
        """
        super().on_resize(width, height)
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

        # Calcula as dimensões do mapa em pixels ANTES de carregar os fundos
        self.map_width_pixels = self.tile_map.width * self.tile_map.tile_width
        self.map_height_pixels = self.tile_map.height * self.tile_map.tile_height
        self.tile_size = self.tile_map.tile_width

        # Carrega as imagens de fundo do arquivo .tmx
        self.background_images = load_background_images(MAP_NAME, self.map_width_pixels)

        # Configuração das listas e camadas
        self.player_list = arcade.SpriteList()
        self.enemy_list = arcade.SpriteList()
        self.enemy_physics_engines = []
        self.hit_cooldown = 0.0
        self.water_tile_centers = []  # Limpa tiles de água

        self.ground_list = self.tile_map.sprite_lists.get(COLLISION_LAYER_NAME)
        self.foreground_list = self.tile_map.sprite_lists.get(
            FOREGROUND_LAYER_NAME, arcade.SpriteList()
        )

        if self.ground_list is None:
            print(
                f"ATENÇÃO: A camada '{COLLISION_LAYER_NAME}' não foi encontrada. Usando SpriteList vazia."
            )
            self.ground_list = arcade.SpriteList()

        # --- LÓGICA CORRIGIDA: PRÉ-CALCULAR PONTOS DE SPAWN DE ÁGUA ---
        for sprite in self.ground_list:
            tile_id = sprite.properties.get("tile_id")
            # Usa o ID corrigido (SWIM_TILE_ID = 59)
            if tile_id == SWIM_TILE_ID:
                # Armazena o centro do tile de água
                self.water_tile_centers.append((sprite.center_x, sprite.center_y))

        if not self.water_tile_centers:
            print(
                f"AVISO: Nenhuma tile de água (ID:{SWIM_TILE_ID}) encontrada na camada '{COLLISION_LAYER_NAME}' para spawn de nadadores!"
            )
        # --- FIM DA LÓGICA DE PRÉ-CÁLCULO ---

        # Configuração do Player
        self.player_sprite = arcade.Sprite(
            PLAYER_IDLE_SPRITE,  # USANDO O NOVO SPRITE DO PLAYER
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

        # Offsets de spawn para corredores e voadores
        spawn_x_offsets = [100, 250, 400]
        spawn_y_offsets = [0, 50, 100]

        # Lista de tiles de água disponíveis para spawn
        available_water_spawns = list(self.water_tile_centers)
        random.shuffle(available_water_spawns)

        for i, traits in enumerate(traits_list):
            # Não é mais necessário passar o image_path, pois Enemy decide
            # o sprite baseado no tipo de traço.
            enemy = Enemy(traits, scale=ENEMY_SCALE)
            enemy.set_target(self.player_sprite)
            enemy_type = traits.get("type")

            if enemy_type == "swimming":
                # --- LÓGICA DE SPAWN PARA NADADORES ---
                if available_water_spawns:
                    # Usa o próximo ponto de água disponível
                    water_x, water_y = available_water_spawns.pop(0)
                    enemy.center_x = water_x

                    # AJUSTE CRÍTICO: Move o inimigo ligeiramente para baixo
                    # para que ele pareça submerso e não flutuando no ar.
                    enemy.center_y = water_y - (self.tile_size * 0.25)

                else:
                    # Fallback se não houver mais tiles de água disponíveis
                    enemy.center_x = (
                        spawn_point_x + spawn_x_offsets[i % len(spawn_x_offsets)]
                    )
                    enemy.center_y = spawn_point_y + self.tile_size * 0.5
                    print(
                        "Aviso: Nadador nasceu em posição padrão devido à falta de tiles de água."
                    )

                enemy.set_physics_engine(
                    None, self.ground_list, SWIM_TILE_ID
                )  # Nadadores não usam Platformer

            else:
                # --- LÓGICA DE SPAWN PARA CORREDORES/VOADORES ---
                offset_index = i % len(spawn_x_offsets)
                y_offset = spawn_y_offsets[offset_index] + self.tile_size * 0.5

                enemy.center_x = spawn_point_x + spawn_x_offsets[offset_index]
                enemy.center_y = spawn_point_y + y_offset

                if enemy_type == "running":
                    runner_engine = arcade.PhysicsEnginePlatformer(
                        enemy, gravity_constant=GRAVITY, walls=self.ground_list
                    )
                    self.enemy_physics_engines.append(runner_engine)
                    enemy.set_physics_engine(runner_engine)

                # Voador não precisa de motor de física, mas precisa do target
                # e já tem a lógica de movimento em update_movement

            self.enemy_list.append(enemy)

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

            # Aplica movimento para inimigos que não usam PhysicsEnginePlatformer
            # Isso inclui o nadador e o voador
            if (
                enemy.traits.get("type") == "flying"
                or enemy.traits.get("type") == "swimming"
            ):
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

        # Aplica movimento e física para inimigos que usam PhysicsEnginePlatformer (Runners)
        for engine in self.enemy_physics_engines:
            engine.update()

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

        START_Y -= LINE_HEIGHT * 2.5

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

        # Desenha as imagens de fundo estáticas
        self.background_images.draw()

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
                screen_width - 275,
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

                # Adiciona o cooldown do ataque do nadador ao log
                attack_cooldown_log = ""
                if enemy.traits["type"] == "swimming":
                    attack_cooldown_log = f" | AC:{enemy.attack_cooldown:.1f}"

                text = f"E{i+1} ({enemy.traits['type'][0]}): F:{temp_fitness:.1f} | R:{enemy.traits['run']:.2f} | J:{enemy.traits['jump']:.2f} | Fl:{enemy.traits['fly']:.2f}{attack_cooldown_log}"
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
