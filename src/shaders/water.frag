#version 330 core

// ---------------------------------------------------------------------------
// FRAGMENT SHADER da água
// Cor da superfície: difuso + especular (Blinn-Phong) + Fresnel + transparência.
// ---------------------------------------------------------------------------

in vec3 v_world_pos;
in vec3 v_normal;

out vec4 f_color;

uniform vec3 u_camera_pos;
uniform vec3 u_light_dir;   // direção da luz (do sol para a cena)

void main() {
    vec3 n = normalize(v_normal);
    vec3 view_dir = normalize(u_camera_pos - v_world_pos);
    vec3 l = normalize(-u_light_dir);

    // Difuso (Lambert) e especular (Blinn-Phong) para o brilho do sol na água.
    float diff = max(dot(n, l), 0.0);
    vec3  h = normalize(l + view_dir);
    float spec = pow(max(dot(n, h), 0.0), 90.0);

    // Fresnel (aproximação de Schlick): olhando de raspão, a água vira espelho.
    float fresnel = 0.02 + 0.98 * pow(1.0 - max(dot(n, view_dir), 0.0), 5.0);

    vec3 c_funda = vec3(0.03, 0.10, 0.18);   // água vista de cima
    vec3 c_rasa  = vec3(0.10, 0.34, 0.44);   // água iluminada
    vec3 c_ceu   = vec3(0.62, 0.72, 0.84);   // reflexo do céu

    vec3 cor = mix(c_funda, c_rasa, diff);
    cor = mix(cor, c_ceu, fresnel);          // reflexo cresce na rasância
    cor += spec * vec3(1.0);                 // ponto de sol

    // Alpha < 1 -> dá para enxergar o terreno submerso por baixo.
    f_color = vec4(cor, 0.80);
}
