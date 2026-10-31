#version 330 core

// ---------------------------------------------------------------------------
// VERTEX SHADER da água  —  ondas de Gerstner
// Executa 1x por vértice do plano de água, a cada frame.
// Base matemática: Fournier & Reeves (1986); forma prática: GPU Gems 1, cap. 1.
// ---------------------------------------------------------------------------

in vec3 in_position;        // ponto do plano plano (x, 0, z), vindo de water.py

out vec3 v_world_pos;       // posição JÁ deslocada pelas ondas
out vec3 v_normal;          // normal analítica da superfície ondulada

uniform mat4 u_view;
uniform mat4 u_proj;
uniform float u_time;       // segundos desde o início (anima as ondas)
uniform float u_sea_level;  // altura de base da água = "nível do mar" ajustável

const float PI = 3.14159265;
const int   N_ONDAS = 6;

// Cada onda tem: direção de propagação (no plano XZ), amplitude, comprimento
// de onda (lambda), velocidade e "steepness" Q (0 = seno redondo, ~1 = crista afiada).
// Somamos ondas de tamanhos diferentes (de um marulho longo a um respingo curto)
// para o mar não ficar repetitivo.
// direções já normalizadas (um inicializador const em GLSL não pode chamar normalize())
const vec2  DIR[N_ONDAS] = vec2[](
    vec2( 0.345603,  0.938401),
    vec2( 0.988940,  0.148341),
    vec2(-0.759235,  0.650773),
    vec2( 0.196116, -0.980581),
    vec2(-0.780869, -0.624695),
    vec2(-0.973528, -0.228477)
);
const float AMP[N_ONDAS]    = float[](1.10, 0.90, 0.50, 0.28, 0.14, 0.07);
const float LAMBDA[N_ONDAS]  = float[](70.0, 48.0, 26.0, 14.0, 7.0, 4.0);
const float SPEED[N_ONDAS]  = float[](8.5,  7.0,  5.5,  4.0,  3.0, 2.2);
const float STEEP[N_ONDAS]  = float[](0.60, 0.55, 0.50, 0.42, 0.35, 0.28);

void main() {
    // Ponto de referência no plano (usado para amostrar a fase de cada onda).
    vec2 xz = in_position.xz;

    vec3 pos = vec3(xz.x, u_sea_level, xz.y);   // ponto sem ondas, na altura do mar
    vec3 nrm = vec3(0.0, 1.0, 0.0);             // normal parte "para cima"

    for (int i = 0; i < N_ONDAS; i++) {
        float w   = 2.0 * PI / LAMBDA[i];       // frequência espacial
        float phi = SPEED[i] * w;               // velocidade de fase (rad/s)
        float wa  = w * AMP[i];
        // Q normalizado por (w*A*num_ondas) para as cristas não se "cruzarem"
        // e formarem laços (limite clássico das ondas de Gerstner).
        float Q   = STEEP[i] / (wa * float(N_ONDAS));

        float theta = w * dot(DIR[i], xz) + phi * u_time;
        float c = cos(theta);
        float s = sin(theta);

        // Deslocamento: horizontal (Gerstner) + vertical (seno).
        pos.x += Q * AMP[i] * DIR[i].x * c;
        pos.z += Q * AMP[i] * DIR[i].y * c;
        pos.y += AMP[i] * s;

        // Normal analítica (derivadas parciais da superfície somada).
        nrm.x -= DIR[i].x * wa * c;
        nrm.z -= DIR[i].y * wa * c;
        nrm.y -= Q * wa * s;
    }

    v_world_pos = pos;
    v_normal    = normalize(nrm);
    gl_Position = u_proj * u_view * vec4(pos, 1.0);
}
