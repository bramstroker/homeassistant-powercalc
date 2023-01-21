import matplotlib.pyplot as plt
import pandas as pd

#df1 = pd.read_csv("LTG002.csv")
df1 = pd.read_csv("LCB001.csv")
df2 = pd.read_csv("ct.csv")
#df2 = pd.read_csv("miliskin.csv")

def plot_data(df, color):
    x = df['bri']
    y = df['watt']
    plt.scatter(x, y, color=color)

plot_data(df1, 'blue')
plot_data(df2, 'red')

plt.legend(['LTG002', 'Miliskin'])
plt.show()
