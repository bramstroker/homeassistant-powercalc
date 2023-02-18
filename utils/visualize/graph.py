import matplotlib.pyplot as plt
import pandas as pd

df1 = pd.read_csv("color_temp2.csv")
df2 = pd.read_csv("color_temp.csv")


def plot_data(df, color):
    x = df['bri']
    y = df['watt']
    plt.scatter(x, y, color=color, marker=".", s=10)


plot_data(df1, 'blue')
plot_data(df2, 'red')

plt.legend(['old', 'new'])
plt.show()
