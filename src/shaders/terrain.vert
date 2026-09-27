#version 330 core

// ---------------------------------------------------------------------------
// VERTEX SHADER do terreno  —  CDLOD com MORPHING (parte 2b)
// ---------------------------------------------------------------------------
//
// Cada bloco do quadtree desenha a mesma grade unitária [0,1]x[0,1]; o shader
// a posiciona no mundo (u_node_offset / u_node_scale) e amostra a altura de
// uma textura (u_heightmap).
//
// O MORPHING resolve as "cracks" e o "popping" entre blocos de níveis
// diferentes (Strugar, 2010):
//   - perto do limite externo do alcance deste bloco, cada vértice "ímpar"
//     da grade desliza suavemente até a posição do vértice "par" vizinho;
//   - com isso a borda do bloco fino passa a ter o MESMO espaçamento da borda
//     do bloco grosso ao lado -> as duas malhas coincidem, sem fresta;
//   - e a transição é gradual -> nada "salta" quando o bloco troca de nível.
// ---------------------------------------------------------------------------

in vec2 in_xz;              // posição na grade unitária, em [0, 1] x [0, 1]

out vec3 v_normal;
out vec3 v_world_pos;
out float v_height;
out float v_node_level;
out float v_morph;         // fator de morph aplicado (para debug/depuração)

uniform mat4 u_view;
uniform mat4 u_proj;
uniform vec3 u_camera_pos;

uniform sampler2D u_heightmap;   // R32F: altura já em unidades de mundo
uniform vec2  u_world_size;      // extensão total do terreno (x, z)
uniform vec2  u_node_offset;     // canto do bloco atual, no mundo
uniform float u_node_scale;      // lado do bloco atual
uniform float u_node_level;      // profundidade do bloco (0 = raiz)

uniform float u_grid_dim;        // nº de subdivisões da grade (32 no LOD, N no ingênuo)
uniform float u_morph_start;     // distância onde o morph começa (0)
uniform float u_morph_end;       // distância onde o morph termina (1)
uniform bool  u_morph_ligado;    // tecla M

float amostrar_altura(vec2 mundo_xz) {
    vec2 uv = mundo_xz / u_world_size + 0.5;   // mundo [-S/2, S/2] -> uv [0, 1]
    return texture(u_heightmap, uv).r;
}

// Desliza os vértices "ímpares" da grade em direção aos "pares" (grade mais grossa).
vec2 aplicar_morph(vec2 g, float k) {
    vec2 resto = fract(g * u_grid_dim * 0.5) * 2.0 / u_grid_dim;
    return g - resto * k;
}

void main() {
    // 1) posição fina no mundo + altura, só para estimar a distância à câmera
    vec2 xz_fino = u_node_offset + in_xz * u_node_scale;
    float h_fino = amostrar_altura(xz_fino);
    float dist = distance(u_camera_pos, vec3(xz_fino.x, h_fino, xz_fino.y));

    // 2) fator de morph: 0 no miolo do alcance do bloco, 1 na borda externa
    float morph = 0.0;
    if (u_morph_ligado) {
        morph = clamp((dist - u_morph_start) / max(u_morph_end - u_morph_start, 0.001),
                      0.0, 1.0);
    }

    // 3) posição definitiva: grade "morphada" -> mundo -> altura da textura
    vec2 g = aplicar_morph(in_xz, morph);
    vec2 xz = u_node_offset + g * u_node_scale;
    float h = amostrar_altura(xz);

    // 4) normal por diferenças finitas (~2,5 texels: alisa o ruído do heightmap)
    vec2 texel = u_world_size / vec2(textureSize(u_heightmap, 0));
    float e = 2.5 * max(texel.x, texel.y);
    float hL = amostrar_altura(xz - vec2(e, 0.0));
    float hR = amostrar_altura(xz + vec2(e, 0.0));
    float hD = amostrar_altura(xz - vec2(0.0, e));
    float hU = amostrar_altura(xz + vec2(0.0, e));
    v_normal = normalize(vec3(hL - hR, 2.0 * e, hD - hU));

    v_world_pos = vec3(xz.x, h, xz.y);
    v_height = h;
    v_node_level = u_node_level;
    v_morph = morph;
    gl_Position = u_proj * u_view * vec4(v_world_pos, 1.0);
}
