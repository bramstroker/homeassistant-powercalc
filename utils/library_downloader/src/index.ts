import express, { Express, Request, Response } from "express";
import dotenv from "dotenv";
import { Octokit } from '@octokit/rest';

dotenv.config();

const app: Express = express();
const port = process.env.PORT || 3000;
const githubToken = process.env.GITHUB_TOKEN;
const owner = "bramstroker"
const repo = "homeassistant-powercalc"


app.get("/", async (req: Request, res: Response) => {

    const octokit = new Octokit({
        auth: githubToken
    });
    const manufacturer = req.query.manufacturer;
    const model = req.query.model;
    if (!manufacturer || !model) {
        console.error("No manufacturer or model passed", manufacturer, model);
        res.status(422).json({message: "No manufacturer or model provided"});
        return;
    }

    try {
        const { data } = await octokit.repos.getContent({
            owner: owner,
            repo: repo,
            path: "custom_components/powercalc/data/" + manufacturer + "/" + model,
        });
        if (!Array.isArray(data)) {
            console.error("No data found", manufacturer, model);
            res.status(404).json({message: "No download url's found"});
            return;
          }
          console.log("Data successfully retrieved", manufacturer, model);
        res.json(data.map((x) => ({"filename": x.name, "url": x.download_url})))
    } catch (error) {
        console.error("Model not found");
        res.status(404).json({message: "Model not found"});
    }
});

app.listen(port, () => {
  console.log(`[server]: Server is running at http://localhost:${port}`);
});