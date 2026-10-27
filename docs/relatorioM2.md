# Relatório de mudanças realizadas para a etapa M2
## Projeto Aplicado Longitudinal — Detecção de drones e aves em imagens de céu


## 1. Resumo da evolução desde a M1

Na M1, o repositório estava concentrado na proposta do problema e na organização de um conjunto inicial de imagens. Na versão M2, foi acrescentado um pipeline executável de segmentação e análise de componentes, uma comparação entre dois métodos de limiarização, arquivos de resultados, testes automatizados e um procedimento para anotar manualmente objetos e medir suas dimensões.

O objetivo do projeto permanece a detecção e futura diferenciação de aves e drones em imagens de céu. A classificação final **não está implementada**; a M2 concentra-se na implementação parcial e na análise da segmentação, conforme permite o enunciado.

## 2. Pipeline implementado

O script `src/run_experiment.py` executa o seguinte fluxo:

1. Localiza as imagens de entrada nas pastas do projeto.
2. Redimensiona imagens grandes proporcionalmente, limitando o maior lado de processamento a 1280 pixels, sem ampliar imagens menores.
3. Converte a imagem para escala de cinza e aplica filtro Gaussiano 5 × 5.
4. Gera uma máscara usando uma de duas configurações:
   - **Otsu global:** limiar global automático;
   - **Limiarização adaptativa Gaussiana:** bloco 31 × 31 e constante C = 5, com ajuste do bloco para imagens pequenas.
5. Aplica abertura morfológica com elemento elíptico 3 × 3.
6. Detecta componentes conectados com conectividade 8 e filtra componentes por área.
7. Calcula atributos como área de pixels do componente, caixa delimitadora, largura, altura, razão de aspecto, perímetro, circularidade e solidez.
8. Exporta máscaras, tabelas CSV, figura comparativa e relatório experimental.

Essas regiões são **componentes candidatos**, não objetos verdadeiros confirmados. Nuvens, sombras, ruído e outras partes do fundo podem ser segmentadas como candidatos; um objeto real também pode desaparecer, fragmentar-se ou unir-se a outro componente.

O script `src/measure_objects.py` complementa o pipeline com uma via de anotação manual. A área da caixa delimitadora (`largura × altura`) inclui pixels de fundo e não deve ser confundida com a área real da silhueta segmentada.

## 3. Experimento comparativo realizado

A pergunta experimental registrada foi se a limiarização adaptativa localiza componentes diferentes da limiarização global de Otsu nas mesmas imagens. As duas configurações foram executadas nas 15 imagens, mantendo comuns o redimensionamento, o filtro Gaussiano, a abertura morfológica e o filtro de componentes. A variável comparada foi o método de limiarização.

### Resultados descritivos registrados

| Indicador | Otsu global | Limiar adaptativo |
|---|---:|---:|
| Componentes candidatos nas 15 imagens | 563 | 1891 |
| Mediana de componentes por imagem | 18 | 18 |
| Mediana da fração de pixels em primeiro plano | 0,516868 | 0,002629 |

Esses números descrevem as máscaras produzidas, **não são medidas de acurácia**. Uma quantidade maior ou menor de componentes, por si só, não indica qual método detectou mais objetos reais.

### Avaliação piloto com referência manual

O arquivo `data/pilot_annotations.csv` contém referência para apenas duas imagens: uma caixa de ave em `LowResolution/Aves 2.jpg` e uma imagem revisada como vazia, `LowResolution/Nada 1.jpg`. O relatório usa IoU mínimo de 0,3 para associar caixas previstas às caixas de referência.

| Indicador piloto | Otsu global | Limiar adaptativo |
|---|---:|---:|
| Verdadeiros positivos (TP) | 1 | 1 |
| Falsos positivos (FP) | 6 | 0 |
| Falsos negativos (FN) | 0 | 0 |
| Precisão | 0,143 | 1,000 |
| Recall | 1,000 | 1,000 |
| F1 | 0,250 | 1,000 |

A anotação da ave foi preparada por inspeção visual com apoio de IA e ainda precisa de revisão independente por um integrante. Portanto, esses valores são **preliminares e limitados a duas imagens**; não justificam afirmar que o método adaptativo é melhor de forma geral. O exemplo negativo mostra que Otsu produziu seis candidatos em uma cena considerada vazia. Em `LowResolution/Drone 2.jpg`, o adaptativo produziu 521 componentes candidatos, o que ilustra fragmentação e falsos candidatos em uma cena com fundo complexo.


## 4. Testes e reprodução

O README documenta a criação do ambiente virtual, instalação das dependências e comandos para executar o experimento, os testes e a ferramenta de anotação. Os testes cobrem máscaras binárias, medidas de componentes sintéticos, pareamento de caixas, cálculo de métricas, redimensionamento, entradas pequenas e máscaras vazias.

Comandos documentados:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

.venv/bin/python src/run_experiment.py --annotations data/pilot_annotations.csv
.venv/bin/python -m unittest discover -s tests -v
```

Para iniciar a anotação manual completa e gerar as medidas:

```bash
.venv/bin/python src/measure_objects.py --annotate
.venv/bin/python src/measure_objects.py --analyze
.venv/bin/python src/run_experiment.py --annotations data/object_annotations.csv
```



## 5. Conclusão

As mudanças encontradas transformam o projeto de uma proposta acompanhada por imagens em uma implementação parcial executável: há código de segmentação, análise de componentes, descritores geométricos, comparação controlada de duas configurações, saídas verificáveis, testes e documentação do protocolo. A ferramenta de anotação também cria um caminho concreto para responder à prioridade do feedback: medir os objetos antes de concluir se sua geometria é suficiente para distinguir aves e drones.

