import express, { Express, Request, Response } from "express";
import dotenv from "dotenv";
import apicache from "apicache";
import { Octokit } from '@octokit/rest';

dotenv.config();

const app: Express = express();
const port = process.env.PORT || 3000;
const githubToken = process.env.GITHUB_TOKEN;
const owner = "bramstroker"
const repo = "homeassistant-powercalc"

apicache.options(
    {
        statusCodes: {
            include: [200],
          },
    }
)

export interface LibraryFile
{
    path: string
    url: string
}

let cache = apicache.middleware

app.get("/download/:manufacturer/:model", cache('1 hour'), async (req: Request, res: Response) => {

    const octokit = new Octokit({
        auth: githubToken
    });
    const manufacturer = req.params.manufacturer;
    const model = req.params.model;
    if (!manufacturer || !model) {
        console.error("No manufacturer or model passed", manufacturer, model);
        res.status(422).json({message: "No manufacturer or model provided"});
        return;
    }

    const fetchContents = async (path: string, newPath: string|null = null): Promise<LibraryFile[]> => {
        if (newPath === null) {
            newPath = path
        }

        const { data } = await octokit.repos.getContent({
            owner: owner,
            repo: repo,
            path: newPath,
        });
    
        if (!Array.isArray(data)) {
            return []
        }
    
        // If it's a directory, recursively fetch its contents
        const subContents = await Promise.all(
            data.map(async (item): Promise<LibraryFile[]> => {
                if (item.type === "file") {
                    // console.log(item)
                    let regex = new RegExp(path, "g");
                    let modifiedPath = item.path.replace(regex, '').substring(1);
                    return [{ path: modifiedPath, url: item.download_url ?? '' }];
                } else if (item.type === "dir") {
                    const newPath = `${path}/${item.name}`;
                    return await fetchContents(path, newPath);
                } else {
                    return []
                }
            })
        );
            
        return subContents.flat()
    };
    
    try {
        const files = await fetchContents(
            "custom_components/powercalc/data/" + manufacturer + "/" + model
        );
        if (files.length === 0) {
            console.error("No data found", manufacturer, model);
            res.status(404).json({message: "No download url's found"});
            return;
          }
          console.log("Data successfully retrieved", manufacturer, model);
            res.json(files)
    } catch (error) {
        console.error("Model not found");
        res.status(404).json({message: "Model not found"});
    }
});

app.get("/library", cache('1 hour'), async (req: Request, res: Response) => {
    const url = "https://raw.githubusercontent.com/bramstroker/homeassistant-powercalc/feat/library-download/custom_components/powercalc/data/library.json"
    console.log("Fetching library")
    const resp = await fetch(url)
    res.json(await resp.json())
});
  
  // add route to display cache index
app.get('/cache/index', (req, res) => {
    res.json(apicache.getIndex())
})

app.get('/cache/clear', (req, res) => {
    res.json(apicache.clear([]))
})

app.listen(port, () => {
    console.log(`[server]: Server is running at http://localhost:${port}`);
});