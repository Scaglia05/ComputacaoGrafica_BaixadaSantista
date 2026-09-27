#version 330 core

// ---------------------------------------------------------------------------
// FRAGMENT SHADER do terreno
// Executa 1x por pixel coberto pela malha. Decide a cor final.
// ---------------------------------------------------------------------------

in vec3 v_normal;
in vec3 v_world_pos;
in float v_height;
in float v_node_level;

out vec4 f_color;

uniform float u_height_scale;   // amplitude vertical do terreno (para normalizar a cor)
uniform vec3  u_light_dir;      // direção da luz (do sol para a cena), no espaço do mundo
uniform vec3  u_camera_pos;     // posição da câmera (para a névoa de distância)
uniform float u_sea_level;      // nível do mar atual — terreno abaixo disso fica "submerso"
uniform bool  u_debug_lod;      // K: pinta cada bloco do quadtree por profundidade

void main() {
    vec3 n = normalize(v_normal);
    vec3 l = normalize(-u_light_dir);          // do fragmento em direção à luz

    // --- 1. Cor base por ALTITUDE + INCLINAÇÃO ---------------------------
    // h = 0 no nível do mar, 1 no ponto mais alto (Serra do Mar).
    float h = clamp(v_height / u_height_scale, 0.0, 1.0);

    vec3 c_costa   = vec3(0.62, 0.58, 0.42);   // restinga / areia
    vec3 c_mata    = vec3(0.17, 0.40, 0.18);   // Mata Atlântica (planície e baixa encosta)
    vec3 c_mata_alta = vec3(0.09, 0.25, 0.13); // encosta densa da serra
    vec3 c_rocha   = vec3(0.44, 0.42, 0.40);   // rocha exposta nos cumes

    vec3 base;
    if (h < 0.04) {
        base = mix(c_costa, c_mata, h / 0.04);
    } else if (h < 0.55) {
        base = mix(c_mata, c_mata_alta, (h - 0.04) / 0.51);
    } else {
        base = mix(c_mata_alta, c_rocha, (h - 0.55) / 0.45);
    }

    // Paredões íngremes (a escarpa da Serra) mostram rocha, não mata.
    float declive = clamp((1.0 - n.y) * 2.2, 0.0, 1.0);
    base = mix(base, c_rocha * 0.85, declive * 0.55);

    // --- 2. Iluminação difusa (lei de Lambert) ----------------------------
    float diff = max(dot(n, l), 0.0);

    // Ambiente + difuso: nada fica 100% preto na sombra.
    vec3 color = base * (0.25 + 0.85 * diff);

    // --- 2b. Faixa SUBMERSA -------------------------------------------------
    // É o objetivo do projeto: mostrar o que fica debaixo d'água conforme o
    // nível do mar sobe. Terreno abaixo de u_sea_level ganha um tom esverdeado
    // escuro, mais forte quanto mais fundo.
    if (v_height < u_sea_level) {
        float prof = clamp((u_sea_level - v_height) / 10.0, 0.0, 1.0);
        vec3 c_submerso = mix(vec3(0.22, 0.34, 0.28), vec3(0.04, 0.13, 0.20), prof);
        color = mix(color, c_submerso, 0.65);
    }

    // --- 2c. DEBUG do LOD ------------------------------------------------
    // Colore cada bloco pela profundidade dele no quadtree: azul = blocos
    // grandes (longe), vermelho = blocos pequenos (perto). Deixa visível o
    // quanto o LOD está subdividindo o terreno ao redor da câmera.
    if (u_debug_lod) {
        vec3 paleta[6] = vec3[](
            vec3(0.20, 0.40, 0.90),   // 0
            vec3(0.20, 0.80, 0.80),   // 1
            vec3(0.30, 0.85, 0.30),   // 2
            vec3(0.95, 0.90, 0.25),   // 3
            vec3(0.95, 0.55, 0.20),   // 4
            vec3(0.90, 0.25, 0.25)    // 5+
        );
        int idx = int(clamp(v_node_level, 0.0, 5.0));
        color = mix(color, paleta[idx], 0.55);
    }

    // --- 3. Névoa de distância (profundidade) ----------------------------
    // Longe da câmera, mistura com uma cor de céu -> dá sensação de escala.
    float dist = length(v_world_pos - u_camera_pos);
    float fog  = clamp((dist - 120.0) / 260.0, 0.0, 0.75);
    vec3 c_ceu = vec3(0.62, 0.72, 0.84);
    color = mix(color, c_ceu, fog);

    f_color = vec4(color, 1.0);
}
