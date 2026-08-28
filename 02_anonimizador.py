# -*- coding: utf-8 -*-
"""
02_anonimizador.py

Algoritmo de Anonimização e Geração de Dados Sintéticos
--------------------------------------------------------
Projeto: Sistema Inteligente de Monitoramento de Energia (IoT residencial)

Lê a base "bruta" (identificável) gerada por 01_gerar_base_simulada.py e
produz uma planilha Excel final na qual NENHUM registro pode ser associado
a um indivíduo específico, combinando duas frentes de proteção:

  (A) MASCARAMENTO / PSEUDONIMIZAÇÃO dos dados reais
      - Supressão de identificadores diretos (nome, e-mail, CPF, senha, IP)
      - Pseudonimização do id_usuario via HMAC-SHA256 (não reversível sem a chave)
      - Generalização de quase-identificadores (endereço -> cidade/estado;
        timestamp exato -> faixa horária)
      - Ruído estatístico (Laplace) nos valores de consumo/potência
      - Checagem de k-anonimato nos grupos de quase-identificadores

  (B) AUGMENTATION / DADOS SINTÉTICOS
      - Geração de perfis e leituras 100% fictícios (Faker + amostragem
        estatística a partir da distribuição agregada, nunca de um único
        indivíduo), na mesma quantidade de ordem de grandeza dos dados reais
      - Mistura (shuffle) dos registros reais mascarados com os sintéticos,
        sem qualquer coluna de sinalização, para que um agente externo não
        consiga distinguir (nem por eliminação) quais linhas vieram de
        pessoas reais.

Saída: dataset_anonimizado_final.xlsx
  - Aba "Perfis_Anonimizados"
  - Aba "Consumo_Anonimizado"
  - Aba "Sumario_Privacidade" (métricas do processo, para auditoria)
"""

import hashlib
import hmac
import random
from datetime import datetime

import numpy as np
import pandas as pd
from faker import Faker

ARQUIVO_ENTRADA = "base_dados_bruta.xlsx"
ARQUIVO_SAIDA = "dataset_anonimizado_final.xlsx"

# Chave secreta usada apenas durante a execução do pipeline para pseudonimizar
# (HMAC). Em produção, deve vir de um cofre de segredos (Vault/KMS) e nunca
# ser versionada ou distribuída junto dos dados de saída.
CHAVE_PSEUDONIMIZACAO = "chave-secreta-do-pipeline-nao-versionar"

K_MINIMO = 3          # limiar de k-anonimato exigido por grupo
EPSILON_RUIDO = 1.0    # parâmetro do ruído de Laplace (privacidade diferencial-like)
FATOR_AUGMENTATION = 1.0  # proporção de registros sintéticos vs. reais (1.0 = dobra o volume)

fake = Faker("pt_BR")
Faker.seed(7)
random.seed(7)
np.random.seed(7)

CIDADES_ESTADOS = [
    ("São Paulo", "SP"), ("Campinas", "SP"), ("Guarulhos", "SP"),
    ("Rio de Janeiro", "RJ"), ("Niterói", "RJ"),
    ("Belo Horizonte", "MG"), ("Uberlândia", "MG"),
    ("Curitiba", "PR"), ("Londrina", "PR"),
    ("Porto Alegre", "RS"),
]

FAIXAS_HORARIAS = [
    (0, 6, "Madrugada (00h-06h)"),
    (6, 12, "Manhã (06h-12h)"),
    (12, 18, "Tarde (12h-18h)"),
    (18, 24, "Noite (18h-24h)"),
]


# ---------------------------------------------------------------------------
# (A) Funções de mascaramento
# ---------------------------------------------------------------------------

def pseudonimizar_id(id_original, chave: str) -> str:
    """Gera um identificador pseudônimo, determinístico e não reversível
    (HMAC-SHA256), preservando a possibilidade de join entre abas sem expor
    o identificador de produção."""
    mensagem = str(id_original).encode()
    digest = hmac.new(chave.encode(), mensagem, hashlib.sha256).hexdigest()
    return f"USR-{digest[:10].upper()}"


def faixa_horaria(dt: datetime) -> str:
    """Generaliza um timestamp exato para uma faixa de 6 horas."""
    hora = dt.hour
    for inicio, fim, rotulo in FAIXAS_HORARIAS:
        if inicio <= hora < fim:
            return rotulo
    return FAIXAS_HORARIAS[-1][2]


def adicionar_ruido_laplace(valor: float, sensibilidade: float, epsilon: float) -> float:
    """Adiciona ruído de Laplace (inspirado em privacidade diferencial) para
    evitar que o valor exato de uma leitura sirva de 'impressão digital'
    para reidentificação por correlação com fontes externas."""
    escala = sensibilidade / epsilon
    ruido = np.random.laplace(loc=0.0, scale=escala)
    return max(0.0, valor + ruido)


def mascarar_usuarios(usuarios_df: pd.DataFrame) -> pd.DataFrame:
    df = usuarios_df.copy()
    df["id_pseudonimo"] = df["id_usuario"].apply(lambda x: pseudonimizar_id(x, CHAVE_PSEUDONIMIZACAO))

    # Supressão total de identificadores diretos
    df = df.drop(columns=[
        "nome_completo", "email", "senha_hash", "cpf",
        "endereco_rua", "numero", "cep", "ip_ultimo_login",
    ])

    # Generalização: bairro é removido, mantém-se apenas cidade/estado
    df = df.drop(columns=["bairro"])

    # Generalização temporal: cadastro/login viram apenas o mês/ano
    df["mes_ano_cadastro"] = pd.to_datetime(df["data_cadastro"]).dt.strftime("%m/%Y")
    df["mes_ano_ultimo_login"] = pd.to_datetime(df["data_ultimo_login"]).dt.strftime("%m/%Y")
    df = df.drop(columns=["data_cadastro", "data_ultimo_login"])

    # id_dispositivo também é pseudonimizado (é um quase-identificador do hub)
    df["id_dispositivo_pseudo"] = df["id_dispositivo"].apply(lambda x: pseudonimizar_id(x, CHAVE_PSEUDONIMIZACAO))
    df = df.drop(columns=["id_dispositivo", "id_usuario"])

    df = df.rename(columns={"id_pseudonimo": "id_perfil"})
    colunas = ["id_perfil", "id_dispositivo_pseudo", "cidade", "estado",
               "mes_ano_cadastro", "mes_ano_ultimo_login"]
    return df[colunas]


def mascarar_consumo(consumo_df: pd.DataFrame) -> pd.DataFrame:
    df = consumo_df.copy()
    df["id_perfil"] = df["id_usuario"].apply(lambda x: pseudonimizar_id(x, CHAVE_PSEUDONIMIZACAO))
    df["id_dispositivo_pseudo"] = df["id_dispositivo"].apply(lambda x: pseudonimizar_id(x, CHAVE_PSEUDONIMIZACAO))

    df["data_hora_leitura"] = pd.to_datetime(df["data_hora_leitura"])
    df["data_leitura"] = df["data_hora_leitura"].dt.strftime("%Y-%m-%d")
    df["faixa_horaria"] = df["data_hora_leitura"].apply(faixa_horaria)

    # Ruído estatístico nos valores mensuráveis (sensibilidade calibrada
    # empiricamente a partir da amplitude típica de cada grandeza)
    df["potencia_instantanea_w"] = df["potencia_instantanea_w"].apply(
        lambda v: round(adicionar_ruido_laplace(v, sensibilidade=15.0, epsilon=EPSILON_RUIDO), 2)
    )
    df["consumo_kwh"] = df["consumo_kwh"].apply(
        lambda v: round(adicionar_ruido_laplace(v, sensibilidade=0.05, epsilon=EPSILON_RUIDO), 4)
    )
    df["valor_estimado_reais"] = (df["consumo_kwh"] * df["tarifa_kwh"]).round(2)

    df = df.drop(columns=["id_usuario", "id_dispositivo", "id_leitura", "data_hora_leitura"])
    colunas = ["id_perfil", "id_dispositivo_pseudo", "data_leitura", "faixa_horaria",
               "potencia_instantanea_w", "consumo_kwh", "tarifa_kwh", "valor_estimado_reais"]
    return df[colunas]


def checar_k_anonimato(consumo_masc: pd.DataFrame, perfis_masc: pd.DataFrame, k: int):
    """Verifica se, ao combinar os quase-identificadores restantes
    (cidade + estado + faixa horária), cada grupo tem pelo menos k
    perfis distintos associados. Retorna um relatório para auditoria."""
    base = consumo_masc.merge(perfis_masc[["id_perfil", "cidade", "estado"]], on="id_perfil", how="left")
    grupos = base.groupby(["cidade", "estado", "faixa_horaria"])["id_perfil"].nunique().reset_index()
    grupos = grupos.rename(columns={"id_perfil": "perfis_distintos_no_grupo"})
    grupos["atende_k_minimo"] = grupos["perfis_distintos_no_grupo"] >= k
    return grupos


# ---------------------------------------------------------------------------
# (B) Geração de dados sintéticos (augmentation)
# ---------------------------------------------------------------------------

def gerar_id_sintetico_no_formato_real(semente: str) -> str:
    """Gera um ID sintético no MESMO formato visual dos pseudônimos reais
    (USR-XXXXXXXXXX), para que um agente externo não consiga separar
    registros reais de registros sintéticos apenas pelo padrão do
    identificador (o que reintroduziria risco de reidentificação por
    eliminação)."""
    digest = hashlib.sha256(semente.encode()).hexdigest()
    return f"USR-{digest[:10].upper()}"


def gerar_perfis_sinteticos(n: int, indice_inicial: int) -> pd.DataFrame:
    perfis = []
    for i in range(n):
        cidade, estado = random.choice(CIDADES_ESTADOS)
        data_fake = fake.date_time_between(start_date="-2y", end_date="now")
        semente = f"sintetico-perfil-{indice_inicial + i}-{fake.uuid4()}"
        semente_dev = f"sintetico-dispositivo-{indice_inicial + i}-{fake.uuid4()}"
        perfis.append({
            "id_perfil": gerar_id_sintetico_no_formato_real(semente),
            "id_dispositivo_pseudo": gerar_id_sintetico_no_formato_real(semente_dev),
            "cidade": cidade,
            "estado": estado,
            "mes_ano_cadastro": data_fake.strftime("%m/%Y"),
            "mes_ano_ultimo_login": fake.date_time_between(start_date="-30d", end_date="now").strftime("%m/%Y"),
        })
    return pd.DataFrame(perfis)


def gerar_consumo_sintetico(perfis_sinteticos: pd.DataFrame, consumo_real_masc: pd.DataFrame) -> pd.DataFrame:
    """Amostra novas leituras a partir da distribuição AGREGADA (média/desvio
    padrão da população, nunca de um indivíduo específico) observada nos
    dados reais já mascarados, garantindo que o padrão estatístico do
    conjunto original seja preservado sem copiar nenhum registro real."""
    media_potencia = consumo_real_masc["potencia_instantanea_w"].mean()
    desvio_potencia = consumo_real_masc["potencia_instantanea_w"].std()
    media_tarifa = consumo_real_masc["tarifa_kwh"].mean()
    desvio_tarifa = consumo_real_masc["tarifa_kwh"].std()

    leituras = []
    for _, perfil in perfis_sinteticos.iterrows():
        n_leituras = random.randint(3, 5)
        tarifa = round(max(0.4, np.random.normal(media_tarifa, desvio_tarifa)), 4)
        for _ in range(n_leituras):
            data_fake = fake.date_time_between(start_date="-60d", end_date="now")
            potencia = max(10.0, np.random.normal(media_potencia, desvio_potencia))
            consumo_kwh = round((potencia / 1000) * random.uniform(0.8, 1.2), 4)
            leituras.append({
                "id_perfil": perfil["id_perfil"],
                "id_dispositivo_pseudo": perfil["id_dispositivo_pseudo"],
                "data_leitura": data_fake.strftime("%Y-%m-%d"),
                "faixa_horaria": faixa_horaria(data_fake),
                "potencia_instantanea_w": round(potencia, 2),
                "consumo_kwh": consumo_kwh,
                "tarifa_kwh": tarifa,
                "valor_estimado_reais": round(consumo_kwh * tarifa, 2),
            })
    return pd.DataFrame(leituras)


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def main():
    usuarios_df = pd.read_excel(ARQUIVO_ENTRADA, sheet_name="Usuarios_Login")
    consumo_df = pd.read_excel(ARQUIVO_ENTRADA, sheet_name="Consumo_Energia")

    # (A) Mascaramento dos dados reais
    perfis_masc = mascarar_usuarios(usuarios_df)
    consumo_masc = mascarar_consumo(consumo_df)

    relatorio_k = checar_k_anonimato(consumo_masc, perfis_masc, K_MINIMO)
    grupos_abaixo_k = relatorio_k[~relatorio_k["atende_k_minimo"]]

    # (B) Geração de dados sintéticos (augmentation)
    n_perfis_sinteticos = max(1, int(len(perfis_masc) * FATOR_AUGMENTATION))
    perfis_sint = gerar_perfis_sinteticos(n_perfis_sinteticos, indice_inicial=1)
    consumo_sint = gerar_consumo_sintetico(perfis_sint, consumo_masc)

    # União + embaralhamento (real mascarado + sintético), sem qualquer
    # coluna que sinalize a origem do registro
    perfis_final = pd.concat([perfis_masc, perfis_sint], ignore_index=True)
    perfis_final = perfis_final.sample(frac=1, random_state=7).reset_index(drop=True)

    consumo_final = pd.concat([consumo_masc, consumo_sint], ignore_index=True)
    consumo_final = consumo_final.sample(frac=1, random_state=7).reset_index(drop=True)

    # Sumário para auditoria interna do time (não expõe nenhum dado pessoal)
    sumario = pd.DataFrame([
        {"metrica": "Registros reais mascarados (perfis)", "valor": len(perfis_masc)},
        {"metrica": "Registros sintéticos gerados (perfis)", "valor": len(perfis_sint)},
        {"metrica": "Total de perfis na saída", "valor": len(perfis_final)},
        {"metrica": "Registros reais mascarados (consumo)", "valor": len(consumo_masc)},
        {"metrica": "Registros sintéticos gerados (consumo)", "valor": len(consumo_sint)},
        {"metrica": "Total de leituras na saída", "valor": len(consumo_final)},
        {"metrica": "k mínimo exigido", "valor": K_MINIMO},
        {"metrica": "Grupos (cidade/estado/faixa) abaixo do k mínimo", "valor": len(grupos_abaixo_k)},
        {"metrica": "Epsilon do ruído de Laplace aplicado", "valor": EPSILON_RUIDO},
    ])

    with pd.ExcelWriter(ARQUIVO_SAIDA, engine="openpyxl") as writer:
        perfis_final.to_excel(writer, sheet_name="Perfis_Anonimizados", index=False)
        consumo_final.to_excel(writer, sheet_name="Consumo_Anonimizado", index=False)
        sumario.to_excel(writer, sheet_name="Sumario_Privacidade", index=False)
        relatorio_k.to_excel(writer, sheet_name="Auditoria_K_Anonimato", index=False)

    print(f"Arquivo final gerado: {ARQUIVO_SAIDA}")
    print(sumario.to_string(index=False))
    if len(grupos_abaixo_k) > 0:
        print("\nAVISO: existem grupos abaixo do k mínimo definido. "
              "Considere aumentar a generalização (ex.: agrupar por região "
              "em vez de cidade) ou aumentar o volume sintético nesses grupos.")


if __name__ == "__main__":
    main()
