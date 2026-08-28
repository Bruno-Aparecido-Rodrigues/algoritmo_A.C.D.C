"""
01_gerar_base_simulada.py

Gera uma base de dados FICTÍCIA (todos os dados são sintéticos desde a
origem — nenhuma pessoa real é representada) simulando o cenário de um
projeto de IoT residencial de monitoramento de consumo de energia elétrica.

A base contém dados IDENTIFICÁVEIS de propósito (nome, e-mail, CPF, senha,
endereço, IP) para servir como INSUMO de teste do algoritmo de
mascaramento/anonimização (02_anonimizador.py). Ou seja: este script simula
"o banco de dados de produção", que na vida real conteria dados sensíveis
reais e por isso nunca deveria ser exposto/compartilhado como está.

Saída: base_dados_bruta.xlsx
  - Aba "Usuarios_Login": dados de cadastro/login dos usuários (~20 registros)
  - Aba "Consumo_Energia": leituras do dispositivo IoT por usuário (~80 registros)
  Total aproximado: 100 registros, conforme solicitado.
"""

import random
import hashlib
from datetime import datetime, timedelta

import pandas as pd
from faker import Faker

fake = Faker("pt_BR")
Faker.seed(42)
random.seed(42)

N_USUARIOS = 20
LEITURAS_POR_USUARIO_MIN = 3
LEITURAS_POR_USUARIO_MAX = 5

CIDADES_ESTADOS = [
    ("São Paulo", "SP"), ("Campinas", "SP"), ("Guarulhos", "SP"),
    ("Rio de Janeiro", "RJ"), ("Niterói", "RJ"),
    ("Belo Horizonte", "MG"), ("Uberlândia", "MG"),
    ("Curitiba", "PR"), ("Londrina", "PR"),
    ("Porto Alegre", "RS"),
]


def gerar_senha_hash_falsa(email: str) -> str:
    """Simula um hash de senha (ex.: como armazenado em produção)."""
    salgado = f"{email}:senha-fake-{random.randint(1000, 9999)}"
    return hashlib.sha256(salgado.encode()).hexdigest()


def gerar_usuarios():
    usuarios = []
    for uid in range(1, N_USUARIOS + 1):
        nome = fake.name()
        email = fake.unique.email()
        cidade, estado = random.choice(CIDADES_ESTADOS)
        data_cadastro = fake.date_time_between(start_date="-2y", end_date="-6M")
        data_ultimo_login = fake.date_time_between(start_date="-30d", end_date="now")
        usuarios.append({
            "id_usuario": uid,
            "nome_completo": nome,
            "email": email,
            "senha_hash": gerar_senha_hash_falsa(email),
            "cpf": fake.cpf(),
            "endereco_rua": fake.street_name(),
            "numero": fake.building_number(),
            "bairro": fake.bairro(),
            "cidade": cidade,
            "estado": estado,
            "cep": fake.postcode(),
            "id_dispositivo": f"HUB-{1000 + uid}",
            "ip_ultimo_login": fake.ipv4_public(),
            "data_cadastro": data_cadastro,
            "data_ultimo_login": data_ultimo_login,
        })
    return pd.DataFrame(usuarios)


def gerar_consumo(usuarios_df: pd.DataFrame):
    leituras = []
    leitura_id = 1
    for _, usuario in usuarios_df.iterrows():
        n_leituras = random.randint(LEITURAS_POR_USUARIO_MIN, LEITURAS_POR_USUARIO_MAX)
        # perfil de consumo "base" do usuário (para os dados ficarem coerentes)
        potencia_media = random.uniform(150, 900)  # Watts
        tarifa = round(random.uniform(0.65, 0.98), 4)  # R$/kWh
        for _ in range(n_leituras):
            data_hora = fake.date_time_between(start_date="-60d", end_date="now")
            potencia_w = max(10, random.gauss(potencia_media, potencia_media * 0.2))
            # energia acumulada no intervalo de leitura (simulando ~1h de coleta)
            consumo_kwh = round((potencia_w / 1000) * random.uniform(0.8, 1.2), 4)
            leituras.append({
                "id_leitura": leitura_id,
                "id_usuario": usuario["id_usuario"],
                "id_dispositivo": usuario["id_dispositivo"],
                "data_hora_leitura": data_hora,
                "potencia_instantanea_w": round(potencia_w, 2),
                "consumo_kwh": consumo_kwh,
                "tarifa_kwh": tarifa,
                "valor_estimado_reais": round(consumo_kwh * tarifa, 2),
            })
            leitura_id += 1
    return pd.DataFrame(leituras)


def main():
    usuarios_df = gerar_usuarios()
    consumo_df = gerar_consumo(usuarios_df)

    usuarios_df = usuarios_df.sort_values("id_usuario")
    consumo_df = consumo_df.sort_values(["id_usuario", "data_hora_leitura"])

    caminho_saida = "base_dados_bruta.xlsx"
    with pd.ExcelWriter(caminho_saida, engine="openpyxl") as writer:
        usuarios_df.to_excel(writer, sheet_name="Usuarios_Login", index=False)
        consumo_df.to_excel(writer, sheet_name="Consumo_Energia", index=False)

    total = len(usuarios_df) + len(consumo_df)
    print(f"Base gerada: {caminho_saida}")
    print(f"  Usuarios_Login: {len(usuarios_df)} registros")
    print(f"  Consumo_Energia: {len(consumo_df)} registros")
    print(f"  Total: {total} registros")


if __name__ == "__main__":
    main()
