# Experimento M2: limiarização global e adaptativa

## Pergunta e protocolo

A limiarização adaptativa localiza componentes distintos da limiarização global de Otsu nas mesmas imagens? Comparam-se duas configurações; pré-processamento, escala, morfologia e filtro de componentes são mantidos constantes.

- Imagens processadas: 15
- Escala: redução proporcional para no máximo 1280 pixels no maior lado; coordenadas das caixas convertidas para a imagem original.
- Pré-processamento comum: escala de cinza e filtro Gaussiano 5 x 5.
- Pós-processamento comum: abertura morfológica com elipse 3 x 3.
- Componentes aceitos: área entre 4 pixels na imagem reduzida e 25% da imagem processada.
- Otsu: limiar global automático, máscara invertida.
- Adaptativo: Gaussiano local, bloco 31 x 31, C=5, máscara invertida.
- Descritores: área de pixels, caixa delimitadora, razão de aspecto, perímetro, circularidade e solidez.

## Resultados quantitativos

A fração de pixels em primeiro plano e a contagem de componentes são indicadores descritivos da segmentação, não acurácia. Um componente pode ser ruído, nuvem ou objeto, e objetos fragmentados podem gerar contagens múltiplas.

| Configuração | Componentes candidatos | Mediana por imagem | Mediana da fração de primeiro plano |
|---|---:|---:|---:|
| otsu | 563 | 18 | 0.516868 |
| adaptive | 1891 | 18 | 0.002629 |

## Resultado por imagem

| Imagem | Configuração | Componentes | Fração de primeiro plano |
|---|---|---:|---:|
| `images/input/HighResolution/Aves 4.jpg` | otsu | 44 | 0.294938 |
| `images/input/HighResolution/Aves 4.jpg` | adaptive | 18 | 0.001817 |
| `images/input/HighResolution/Aves 5.jpg` | otsu | 280 | 0.609183 |
| `images/input/HighResolution/Aves 5.jpg` | adaptive | 7 | 0.002017 |
| `images/input/HighResolution/Drone 3.jpg` | otsu | 19 | 0.588965 |
| `images/input/HighResolution/Drone 3.jpg` | adaptive | 33 | 0.002629 |
| `images/input/HighResolution/Drone e Aves 2.jpg` | otsu | 26 | 0.441116 |
| `images/input/HighResolution/Drone e Aves 2.jpg` | adaptive | 6 | 0.004069 |
| `images/input/LowResolution/Aves 1.jpg` | otsu | 65 | 0.456234 |
| `images/input/LowResolution/Aves 1.jpg` | adaptive | 1 | 0.000234 |
| `images/input/LowResolution/Aves 2.jpg` | otsu | 1 | 0.001814 |
| `images/input/LowResolution/Aves 2.jpg` | adaptive | 1 | 0.001995 |
| `images/input/LowResolution/Aves 3.jpg` | otsu | 23 | 0.003941 |
| `images/input/LowResolution/Aves 3.jpg` | adaptive | 32 | 0.004881 |
| `images/input/LowResolution/Drone 1.jpg` | otsu | 3 | 0.669538 |
| `images/input/LowResolution/Drone 1.jpg` | adaptive | 5 | 0.000413 |
| `images/input/LowResolution/Drone 2.jpg` | otsu | 32 | 0.516868 |
| `images/input/LowResolution/Drone 2.jpg` | adaptive | 521 | 0.040419 |
| `images/input/LowResolution/Drone 3.jpg` | otsu | 10 | 0.622755 |
| `images/input/LowResolution/Drone 3.jpg` | adaptive | 453 | 0.025549 |
| `images/input/LowResolution/Drone 4.jpg` | otsu | 18 | 0.614039 |
| `images/input/LowResolution/Drone 4.jpg` | adaptive | 364 | 0.023534 |
| `images/input/LowResolution/Drone 5.jpg` | otsu | 8 | 0.837891 |
| `images/input/LowResolution/Drone 5.jpg` | adaptive | 3 | 0.000830 |
| `images/input/LowResolution/Drone 6.jpg` | otsu | 13 | 0.513599 |
| `images/input/LowResolution/Drone 6.jpg` | adaptive | 159 | 0.015344 |
| `images/input/LowResolution/Drone e Ave 1.jpg` | otsu | 15 | 0.586802 |
| `images/input/LowResolution/Drone e Ave 1.jpg` | adaptive | 288 | 0.017338 |
| `images/input/LowResolution/Nada 1.jpg` | otsu | 6 | 0.279886 |
| `images/input/LowResolution/Nada 1.jpg` | adaptive | 0 | 0.000000 |

## Avaliação com caixas de referência

Foram revisadas 2 imagens no CSV de referência; as métricas são preliminares e valem apenas para esse subconjunto. Usa-se IoU >= 0.3 para parear caixas preditas e manuais.

| Configuração | TP | FP | FN | Precisão | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| otsu | 1 | 6 | 0 | 0.143 | 1.000 | 0.250 |
| adaptive | 1 | 0 | 0 | 1.000 | 1.000 | 1.000 |

A caixa da ave no piloto foi preparada por inspeção visual com apoio de IA e ainda requer revisão independente de um integrante; os resultados são preliminares. Em `LowResolution/Aves 2.jpg`, ambos os métodos produzem um candidato pareado à caixa. Em `LowResolution/Nada 1.jpg`, Otsu produz seis falsos candidatos e o adaptativo nenhum. Isso exemplifica um sucesso e uma falha, mas não valida desempenho fora destas duas imagens.

## Interpretação, sucessos e limitações

A comparação mantém as mesmas imagens, escala de processamento, filtro Gaussiano, morfologia e critérios de área; varia somente o método de limiarização. A fração de primeiro plano e o número de componentes mostram diferenças entre configurações, mas não permitem declarar uma vencedora sem referência manual.

Inspecione a figura `segmentation_comparison.jpg` junto à tabela por imagem. Em `LowResolution/Drone 2.jpg`, o adaptativo produz 521 componentes candidatos, ilustrando fragmentação e falsos candidatos em céu nublado. Nuvens e regiões escuras podem ser confundidas com objetos; objetos muito pequenos podem desaparecer com a abertura morfológica ou ficar abaixo do limite de área. Objetos próximos podem se unir e uma silhueta pode se fragmentar.

## Artefatos e próximo passo

- `segmentation_comparison.csv`: métricas descritivas por imagem.
- `segmented_components.csv`: descritores dos componentes.
- `masks/`: máscaras binárias das duas configurações.
- `segmentation_comparison.jpg`: figura comparativa com a entrada e as detecções candidatas.
- `measurement_summary.md` e `object_measurements.csv`: saídas complementares do script de anotação manual, quando executado.
- `data/pilot_annotations.csv`: referência piloto de duas imagens; a equipe deve revisar essa anotação antes de considerá-la validada.

Na próxima execução, complete e revise as caixas de referência; avalie separadamente segmentação (precisão/recall de caixas) e descritores de classe. O conjunto atual é pequeno e heterogêneo; uma divisão treino/teste por imagem só deve ser feita quando houver dados suficientes e as origens relacionadas estiverem identificadas. Nenhum classificador é treinado neste experimento.
