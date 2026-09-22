import provtrack
provtrack.activate(verbose=True)

import pandas as pd

df = pd.read_csv("https://raw.githubusercontent.com/datasciencedojo/datasets/master/titanic.csv")
df = provtrack.wrap(df)

df = df.dropna(subset=["Age", "Embarked"])
df = df[df["Age"] > 18]
df = df.rename(columns={"Survived": "label"})

graph = provtrack.lineage()
print(graph.summary())
print()
print("--- MERMAID ---")
print(graph.to_mermaid())
