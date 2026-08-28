# Pipeline de Anonimização e Geração de Dados Sintéticos — Monitoramento de Energia (IoT)

Este repositório contém um pipeline de dados em Python que recebe uma base
**identificável** (dados de login + leituras de consumo de energia de um
projeto de IoT residencial) e produz uma planilha Excel **anonimizada**,
combinando **mascaramento de dados reais** com **geração de dados
sintéticos (augmentation)**. O objetivo é impedir a reidentificação de
qualquer morador a partir dos dados publicados/compartilhados.

## Estrutura do repositório

```
├── 01_gerar_base_simulada.py     # Gera a base fictícia "de produção" (entrada de teste)
├── 02_anonimizador.py            # Algoritmo principal de anonimização + augmentation
├── base_dados_bruta.xlsx         # Saída de (1): dados fictícios, mas com PII simulada
├── dataset_anonimizado_final.xlsx# Saída de (2): entregável final, seguro para compartilhar
└── README.md
```

> **Importante:** `base_dados_bruta.xlsx` existe apenas para simular o banco
> de dados de produção e permitir testar o algoritmo. Ele contém PII
> simulada (nome, e-mail, CPF, senha, IP) e **não deveria ser tratado como
> um artefato seguro para distribuição** — é justamente o problema que o
> `02_anonimizador.py` resolve.

## Como executar

```bash
pip install pandas openpyxl faker numpy
python 01_gerar_base_simulada.py   # gera base_dados_bruta.xlsx
python 02_anonimizador.py          # lê a base bruta e gera dataset_anonimizado_final.xlsx
```

## Modelo de dados de entrada (`base_dados_bruta.xlsx`)

| Aba | Conteúdo | Registros |
|---|---|---|
| `Usuarios_Login` | Cadastro/login: nome, e-mail, senha (hash), CPF, endereço completo, IP, dispositivo | ~20 |
| `Consumo_Energia` | Leituras do hub IoT (SCT-013/ESP32): potência instantânea, consumo em kWh, tarifa, valor estimado | ~76 |

## Técnicas aplicadas em `02_anonimizador.py`

### 1. Mascaramento dos dados reais

| Técnica | O que faz | Onde é aplicada |
|---|---|---|
| **Supressão de identificadores diretos** | Remove por completo colunas que identificam a pessoa de forma inequívoca | `nome_completo`, `email`, `senha_hash`, `cpf`, `endereco_rua`, `numero`, `cep`, `ip_ultimo_login` |
| **Pseudonimização (HMAC-SHA256)** | Substitui `id_usuario` e `id_dispositivo` por um token derivado de uma chave secreta do pipeline. É determinístico (permite `JOIN` entre as abas) mas **não reversível** sem a chave, e não guarda nenhuma relação matemática óbvia com o ID original | `id_perfil`, `id_dispositivo_pseudo` |
| **Generalização de quase-identificadores (espacial)** | Reduz a granularidade do endereço, mantendo apenas `cidade`/`estado` (remove rua, número, bairro, CEP) | Perfis |
| **Generalização de quase-identificadores (temporal)** | Datas de cadastro/login viram `mês/ano`; o horário exato de cada leitura vira uma **faixa de 6h** (madrugada/manhã/tarde/noite) | Perfis e leituras |
| **Ruído estatístico (mecanismo inspirado em privacidade diferencial, ruído de Laplace)** | Adiciona uma perturbação aleatória calibrada (`epsilon`) aos valores de potência e consumo, para que o valor exato de uma leitura não sirva de "impressão digital" para cruzamento com fontes externas (ex.: fatura real da concessionária) | `potencia_instantanea_w`, `consumo_kwh` |
| **Auditoria de k-anonimato** | Agrupa os registros por `cidade + estado + faixa_horaria` e verifica se cada combinação de quase-identificadores está associada a, no mínimo, `k` perfis distintos (`K_MINIMO = 3`). Grupos abaixo do limiar são reportados na aba `Auditoria_K_Anonimato` para que o time decida se generaliza mais (ex.: agrupar por região) ou aumenta o volume sintético naquele grupo | Todo o dataset |

### 2. Geração de dados sintéticos (augmentation)

- Novos perfis e leituras são criados **do zero**, com `Faker` (para atributos
  categóricos plausíveis, como cidade) e amostragem estatística
  (`numpy.random.normal`) a partir da **média e desvio-padrão agregados da
  população real já mascarada** — nunca copiando ou perturbando o registro
  de uma pessoa específica.
- O volume sintético gerado é proporcional ao volume real (`FATOR_AUGMENTATION`),
  por padrão dobrando a base.
- Os identificadores sintéticos são gerados **no mesmo formato visual**
  dos pseudônimos reais (`USR-XXXXXXXXXX`), e todos os registros (reais
  mascarados + sintéticos) são **embaralhados juntos** (`sample(frac=1)`)
  antes da exportação, sem qualquer coluna de sinalização de origem.
  Isso é proposital: uma coluna `"é_sintetico"` permitiria a um atacante
  simplesmente filtrar os registros reais remanescentes, reintroduzindo o
  risco de reidentificação por eliminação.

## Saída (`dataset_anonimizado_final.xlsx`)

| Aba | Conteúdo |
|---|---|
| `Perfis_Anonimizados` | Perfis pseudonimizados (reais + sintéticos), sem PII |
| `Consumo_Anonimizado` | Leituras de consumo pseudonimizadas (reais + sintéticas) |
| `Sumario_Privacidade` | Métricas do processo (quantos registros reais/sintéticos, epsilon usado, k mínimo) — uso interno do time, não é PII |
| `Auditoria_K_Anonimato` | Tamanho de cada grupo de quase-identificadores, para revisão manual |

## Limitações e trabalhos futuros

- O `K_MINIMO` configurado (3) é um ponto de partida didático; em produção,
  o valor deve ser definido junto da equipe jurídica/DPO com base no
  apetite de risco do projeto (LGPD, Art. 12).
- A aba `Auditoria_K_Anonimato` pode indicar grupos abaixo do limiar quando
  a amostra de teste é pequena — nesse caso, recomenda-se generalizar mais
  (ex.: agrupar por região/estado em vez de cidade) ou aumentar
  `FATOR_AUGMENTATION` antes de publicar os dados.
- A chave `CHAVE_PSEUDONIMIZACAO` está hardcoded apenas para fins
  didáticos deste protótipo; em produção deve vir de um cofre de segredos
  (ex.: HashiCorp Vault, AWS KMS) e nunca ser versionada.
- O ruído de Laplace (`EPSILON_RUIDO`) é uma aproximação didática de
  privacidade diferencial, não uma implementação formalmente auditada
  (ex.: via biblioteca `diffprivlib` ou `opendp`) — recomendado para uma
  próxima iteração caso o projeto avance para produção.
