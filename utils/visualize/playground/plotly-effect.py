import pandas as pd
import plotly.express as px

# Load data
data = pd.read_csv("effect.csv")

# Create interactive line plot
fig = px.line(data, x="bri", y="watt", color="effect", markers=True,
              title="Power Consumption vs Brightness for Different Effects",
              labels={"bri": "Brightness", "watt": "Power Consumption (Watt)"})

# Show interactive plot
fig.show()
