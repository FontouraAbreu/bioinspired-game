# -*- coding: utf-8 -*-
"""
POC 2D de Plataforma Simples com Tiled Map e Inimigos Evolutivos.

Foco: Carregar mapa TMX para design de nível, spawn correto do jogador e
inclusão de inimigos com lógica de movimento, incluindo salto.
"""
import arcade
import random

# --- Configurações do Jogo ---
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
SCREEN_TITLE = "Plataforma Simples com Mapa Tiled"

# Nome do arquivo de mapa Tiled
MAP_NAME = "assets/test_level.tmx"

# Constantes do Jogo
PLAYER_MOVEMENT_SPEED = 5  # Velocidade do jogador
PLAYER_JUMP_FORCE = 10
GRAVITY = 0.7

# --- CONSTANTES DE MOVIMENTO DO INIMIGO TERRESTRE ---
# VALOR AJUSTADO: A velocidade máxima foi reduzida de 6.0 para 4.0
ENEMY_MAX_RUN_SPEED = 4.0
ENEMY_PERCEPTION_RANGE = 400
ENEMY_ACCELERATION = 0.1
ENEMY_FRICTION = 0.95
ENEMY_DRIFT_DECELERATION = 0.6


# Constantes da Câmera
DEAD_ZONE_X = 150

# Cor de Fundo
BACKGROUND_COLOR = (173, 216, 230)  # Azul Claro (Céu)

# Multiplicadores de Habilidade (para inimigos)
TRAIT_MULTIPLIER = 0.5
MAX_TRAIT_VALUE = 5

# --- CONSTANTES DE VOO ADAPTATIVO (Frequência Dinâmica) ---
BAT_FLAP_LIFT = 8.0  # Força constante aplicada em cada flap
BAT_GRAVITY_EFFECT = -0.3
HORIZONTAL_WOBBLE = 0.5

# Forças Proporcionais (Controlando a FREQUÊNCIA do flap)
BAT_FLAP_BASE_INTERVAL = 0.5  # Segundos - Intervalo para pairar (BASE)
BAT_FLAP_MIN_INTERVAL = 0.2
BAT_FLAP_MAX_INTERVAL = 1.2
BAT_FLAP_INTERVAL_ADJUSTMENT_FACTOR = 0.005
BAT_HEIGHT_DEAD_ZONE = 20

# --- NOVAS CONSTANTES DE BALANCEAMENTO (PARA PERMITIR FUGA) ---
BAT_PROXIMITY_RANGE = 60
BAT_PROXIMITY_DEAD_ZONE_BONUS = 50
BAT_PROXIMITY_HORIZONTAL_DRAG = 0.7


class Enemy(arcade.Sprite):
    """
    Classe base para os inimigos com traços evolutivos.
    """

    def __init__(self, traits: dict, image_path: str, scale: float = 0.4):
        # Verifica se o caminho é um recurso do Arcade ou se queremos um círculo simples
        if image_path.startswith(":resources:") or image_path == "circle_placeholder":
            # Cria um círculo vermelho sólido como placeholder temporário
            radius = int(20 * scale / 0.4)  # Ajusta o raio baseado na escala
            color = arcade.color.RED
            super().__init__(None, scale)
            self.texture = arcade.make_circle_texture(radius * 2, color)
            self.width = radius * 2
            self.height = radius * 2

            # Define a cor do sprite com base no traço de velocidade principal (apenas para visualização)
            if "run" in traits:
                # Matiza o sprite com base na eficiência de corrida (vermelho mais claro = mais rápido)
                run_norm = traits["run"] / MAX_TRAIT_VALUE
                # Garante que as cores são inteiros (muda a cor para variar o tone)
                blue_value = int(255 * (1 - run_norm * 0.5))
                self.color = (255, blue_value, blue_value)
            else:
                self.color = arcade.color.RED
        else:
            # Tenta carregar o sprite normal se não for um recurso
            super().__init__(image_path, scale)

            # Define a cor do sprite com base no traço de velocidade principal (apenas para visualização)
            if "run" in traits:
                # Matiza o sprite com base na eficiência de corrida (vermelho mais claro = mais rápido)
                run_norm = traits["run"] / MAX_TRAIT_VALUE

                # Garante que as cores são inteiros
                green_blue_value = int(255 * (1 - run_norm * 0.5))
                self.color = (255, green_blue_value, green_blue_value)
            else:
                self.color = (255, 100, 100)  # Vermelho Padrão

        # Traços de eficiência: 'run', 'fly' e 'jump' (de 1 a 5)
        self.traits = traits

        # Define a velocidade máxima de corrida e voo com base nos traços
        # A velocidade de corrida é escalonada até ENEMY_MAX_RUN_SPEED (4.0)
        self.max_run_speed = (
            self.traits.get("run", 1) / MAX_TRAIT_VALUE
        ) * ENEMY_MAX_RUN_SPEED
        self.max_fly_speed = self.traits.get("fly", 1) * TRAIT_MULTIPLIER

        # Timer para controlar a frequência do "flap" de voo
        self.flap_timer = random.uniform(0, BAT_FLAP_BASE_INTERVAL)

        # Motor de física e variáveis de salto
        self.physics_engine = None
        self.jump_cooldown = 0.0
        self.JUMP_COOLDOWN_TIME = 1.0

        # Variáveis para a nova lógica de perseguição/drift
        self.is_drifting = False

        # Referência ao jogador (target)
        self.player_target = None

    def set_target(self, player_sprite):
        """Define o sprite do jogador como alvo."""
        self.player_target = player_sprite

    def set_physics_engine(self, engine):
        """Define o motor de física para este inimigo."""
        self.physics_engine = engine

    def update_movement(self, delta_time):
        """Lógica básica de movimento para perseguir o jogador, incluindo salto e voo com flap."""
        if not self.player_target:
            return

        # Atualiza o cooldown do salto
        if self.jump_cooldown > 0:
            self.jump_cooldown -= delta_time

        # 1. Movimento Horizontal (Correr/Seguir com Aceleração/Fricção/Drift)
        if self.traits.get("run", 0) > 0 and self.traits.get("type") != "flying":

            distance_to_player = self.player_target.center_x - self.center_x

            # --- PERCEPÇÃO: Só persegue se estiver dentro do alcance ---
            if abs(distance_to_player) > ENEMY_PERCEPTION_RANGE:
                self.change_x *= ENEMY_FRICTION
                self.is_drifting = False

                # O motor de física do inimigo é atualizado no on_update.
                return

            # --- 1a. Determina a direção alvo ---
            desired_direction = 0
            if distance_to_player < 0:  # Jogador está à esquerda
                desired_direction = -1
            elif distance_to_player > 0:  # Jogador está à direita
                desired_direction = 1

            # --- 1b. Lógica de DRIFT/Inversão (Se a velocidade atual é oposta à desejada) ---
            if desired_direction != 0:
                if (desired_direction * self.change_x < 0) and (
                    abs(self.change_x) > 0.5
                ):
                    self.is_drifting = True
                else:
                    self.is_drifting = False

            # --- 1c. Aplica o movimento ---
            if self.is_drifting:
                self.change_x *= ENEMY_DRIFT_DECELERATION
                if abs(self.change_x) < 0.2:
                    self.is_drifting = False
                    self.change_x = 0

            elif desired_direction != 0:
                self.change_x += ENEMY_ACCELERATION * desired_direction

            else:  # Parando (desired_direction == 0)
                self.change_x *= ENEMY_FRICTION

            # --- 1d. Limita a velocidade horizontal ---
            self.change_x = max(
                min(self.change_x, self.max_run_speed), -self.max_run_speed
            )

            # Lógica de Salto (exclusiva para inimigos terrestres)
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

        # 2. Movimento Vertical (Voar - ESTILO MORCEGO)
        if self.traits.get("fly", 0) > 0 and self.traits.get("type") == "flying":

            # --- Lógica de Voo ---

            # 2a. Aplica efeito de gravidade/queda (para forçar o flap)
            self.change_y += BAT_GRAVITY_EFFECT

            # --- 2b. Lógica de Frequência Dinâmica (Intervalo Proporcional) ---
            dy = self.player_target.center_y - self.center_y
            dx = abs(self.player_target.center_x - self.center_x)

            # --- AJUSTE DE BALANCEAMENTO (Stutter por Proximidade) ---
            vertical_dead_zone = BAT_HEIGHT_DEAD_ZONE
            if dx < BAT_PROXIMITY_RANGE:
                vertical_dead_zone += BAT_PROXIMITY_DEAD_ZONE_BONUS
                self.change_x *= BAT_PROXIMITY_HORIZONTAL_DRAG

            # 1. Ajuste base: calcula o ajuste do intervalo.
            interval_adjustment = -dy * BAT_FLAP_INTERVAL_ADJUSTMENT_FACTOR

            # 2. Zona Morta: se a diferença de altura for pequena, o ajuste é zero
            if abs(dy) < vertical_dead_zone:
                interval_adjustment = 0

            # 3. Calcula o intervalo atual e limita
            current_interval = BAT_FLAP_BASE_INTERVAL + interval_adjustment
            current_interval = max(
                min(current_interval, BAT_FLAP_MAX_INTERVAL), BAT_FLAP_MIN_INTERVAL
            )

            # 4. Flap se o timer exceder o intervalo CALCULADO DINAMICAMENTE
            self.flap_timer += delta_time
            if self.flap_timer >= current_interval:
                self.flap_timer = 0
                self.change_y = BAT_FLAP_LIFT

            # 2c. Movimento Horizontal Despreciso (Acompanhar Jogador)

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

            # 2d. Limita a velocidade vertical (usa o traço 'fly' como um limite)
            max_v_speed = self.traits.get("fly", 1) * TRAIT_MULTIPLIER * 1.5
            self.change_y = max(min(self.change_y, max_v_speed), -max_v_speed)


class MyGame(arcade.Window):
    """
    Classe Principal do Jogo - Carrega o Tiled Map e gerencia o Player e Inimigos
    """

    def __init__(self, width, height, title):
        super().__init__(width, height, title)
        arcade.set_background_color(BACKGROUND_COLOR)

        # Listas de Sprites
        self.player_list = None
        self.enemy_list = None
        self.tile_map = None
        self.ground_list = None
        self.player_sprite = None

        # Variáveis globais de mapa
        self.map_width_pixels = 0
        self.tile_size = 32

        # Câmeras
        self.camera = arcade.camera.Camera2D()
        self.gui_camera = arcade.camera.Camera2D()

        # Sistema de Física
        self.physics_engine = None
        self.enemy_physics_engines = []

        # Estado de Movimento (Resolvendo o problema de controle)
        self.left_pressed = False
        self.right_pressed = False

    def setup(self):
        """Configura o jogo, carregando o mapa Tiled."""
        self.player_list = arcade.SpriteList()
        self.enemy_list = arcade.SpriteList()
        self.enemy_physics_engines = []

        # --- 1. Carregamento do Mapa Tiled ---
        layer_options = {
            "Tile Layer 1": {
                "use_spatial_hash": True,
            },
            "Player Start": {},
        }

        self.tile_map = arcade.load_tilemap(
            MAP_NAME, scaling=1.0, layer_options=layer_options
        )

        self.map_width_pixels = self.tile_map.width * self.tile_map.tile_width
        self.tile_size = self.tile_map.tile_width

        self.ground_list = self.tile_map.sprite_lists["Tile Layer 1"]

        # --- 2. Configuração do Player ---
        self.player_sprite = arcade.Sprite(
            ":resources:images/animated_characters/female_person/femalePerson_idle.png",
            0.4,  # Escala
        )
        self.player_sprite.width = self.tile_size * 0.8
        self.player_sprite.height = self.tile_size * 0.8

        # --- 2b. ENCONTRAR O PONTO DE SPAWN ---
        player_spawn_layer = self.tile_map.object_lists.get("Player Start")

        spawn_point_found = False
        if player_spawn_layer and player_spawn_layer[0]:
            spawn_point = player_spawn_layer[0][0]
            spawn_point_x = spawn_point[0]
            spawn_point_y = spawn_point[1]

            self.player_sprite.center_x = spawn_point_x
            self.player_sprite.center_y = spawn_point_y

            spawn_point_found = True

        if not spawn_point_found:
            print(
                "AVISO: Camada de Objeto 'Player Start' não encontrada ou vazia no TMX."
            )
            print("Usando posição de fallback: X=50, Y=200.")
            self.player_sprite.center_x = 50
            self.player_sprite.center_y = 200

        self.player_list.append(self.player_sprite)

        # --- 3. Configuração do Motor de Física do Player ---
        self.physics_engine = arcade.PhysicsEnginePlatformer(
            self.player_sprite, gravity_constant=GRAVITY, walls=self.ground_list
        )

        # --- 4. Configuração dos Inimigos ---

        # Inimigo Corredor
        runner_traits = {"run": 5, "fly": 1, "jump": 5, "type": "running"}
        enemy_runner = Enemy(runner_traits, "circle_placeholder", 0.4)
        enemy_runner.set_target(self.player_sprite)
        enemy_runner.center_x = self.player_sprite.center_x + 150
        enemy_runner.center_y = self.player_sprite.center_y
        self.enemy_list.append(enemy_runner)

        runner_engine = arcade.PhysicsEnginePlatformer(
            enemy_runner, gravity_constant=GRAVITY, walls=self.ground_list
        )
        self.enemy_physics_engines.append(runner_engine)
        enemy_runner.set_physics_engine(runner_engine)

        # Inimigo Voador
        flying_traits = {"run": 1, "fly": 5, "jump": 1, "type": "flying"}
        enemy_flyer = Enemy(flying_traits, "circle_placeholder", 0.4)
        enemy_flyer.set_target(self.player_sprite)
        enemy_flyer.center_x = self.player_sprite.center_x + 300
        enemy_flyer.center_y = self.player_sprite.center_y + 100
        self.enemy_list.append(enemy_flyer)

        # 5. Resetar o estado de movimento
        self.left_pressed = False
        self.right_pressed = False

        # Posição inicial da câmera
        self.camera.position = (self.player_sprite.center_x, 0)

    def apply_movement(self):
        """Calcula a mudança de X do jogador com base nas teclas pressionadas."""
        self.player_sprite.change_x = 0

        if self.left_pressed and not self.right_pressed:
            self.player_sprite.change_x = -PLAYER_MOVEMENT_SPEED
        elif self.right_pressed and not self.left_pressed:
            self.player_sprite.change_x = PLAYER_MOVEMENT_SPEED

    def on_key_press(self, key, modifiers):
        """Atualiza o estado da tecla pressionada e recalcula o movimento."""
        if key == arcade.key.LEFT:
            self.left_pressed = True
        elif key == arcade.key.RIGHT:
            self.right_pressed = True
        elif key == arcade.key.UP or key == arcade.key.SPACE:
            if self.physics_engine.can_jump():
                self.player_sprite.change_y = PLAYER_JUMP_FORCE

        self.apply_movement()

    def on_key_release(self, key, modifiers):
        """Atualiza o estado da tecla solta e recalcula o movimento."""
        if key == arcade.key.LEFT:
            self.left_pressed = False
        elif key == arcade.key.RIGHT:
            self.right_pressed = False

        self.apply_movement()

    def center_camera_to_player(self):
        """
        Move a câmera suavemente, usando uma zona morta (dead-zone)
        horizontalmente, mas trava verticalmente.
        """
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
        self.physics_engine.update()

        # --- Lógica de Inimigos ---
        for enemy in self.enemy_list:
            enemy.update_movement(delta_time)

            if enemy.traits.get("type") == "flying":
                enemy.update()

        for engine in self.enemy_physics_engines:
            engine.update()

        self.enemy_list.update()
        # --- Fim da Lógica de Inimigos ---

        self.center_camera_to_player()

        self.camera.position = self.player_sprite.position

        if self.player_sprite.center_y < -100:
            self.setup()

    def on_draw(self):
        """Renderiza a tela."""
        self.clear()

        self.camera.use()

        if self.ground_list:
            self.ground_list.draw()

        self.player_list.draw()

        self.enemy_list.draw()

        self.gui_camera.use()

        arcade.draw_text(
            "AI Terrestre: Velocidade Máxima reduzida para 4.0 (Mais Lento).",
            10,
            SCREEN_HEIGHT - 30,
            arcade.color.BLACK,
            18,
        )


def main():
    """Função principal para rodar o jogo."""
    window = MyGame(SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_TITLE)
    window.setup()
    arcade.run()


if __name__ == "__main__":
    main()
