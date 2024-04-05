import express, { Express, Request, Response, NextFunction } from "express";
import dotenv from "dotenv";
import apicache from "apicache";
import { Octokit } from "@octokit/rest";
import pino from "pino";
import promClient from "prom-client";

dotenv.config();

const port = process.env.PORT || 3000;
const githubToken = process.env.GITHUB_TOKEN;
const bearerToken = process.env.BEARER_TOKEN;
const owner = "bramstroker";
const repo = "homeassistant-powercalc";

const app: Express = express();
const logger = pino();
const collectDefaultMetrics = promClient.collectDefaultMetrics;
const Registry = promClient.Registry;
const register = new Registry();
collectDefaultMetrics({ register });

export interface LibraryFile {
  path: string;
  url: string;
}

let promDownloadCounter = new promClient.Counter({
  name: "powercalc_download",
  help: "Number of downloads for a profile",
  labelNames: ["manufacturer", "model"] as const,
});
register.registerMetric(promDownloadCounter);

// API cache middleware
apicache.options({
  statusCodes: {
    include: [200],
  },
});
const cache = apicache.middleware;

// Authorization middleware for private endpoints
const verifyToken = (req: Request, res: Response, next: NextFunction) => {
  const token = req.headers.authorization?.split(" ")[1];
  if (!token) {
    res.status(401).send("Authentication required.");
    return;
  }
  if (token != bearerToken) {
    res.status(403).send("Invalid token.");
    return;
  }
  next();
};

app.get(
  "/download/:manufacturer/:model",
  cache("1 hour"),
  async (req: Request, res: Response) => {
    const octokit = new Octokit({
      auth: githubToken,
    });
    const manufacturer = req.params.manufacturer;
    const model = req.params.model;
    if (!manufacturer || !model) {
      logger.error(
        "Manufacturer %s or model %s not provided",
        manufacturer,
        model
      );
      res.status(422).json({ message: "No manufacturer or model provided" });
      return;
    }

    const fetchContents = async (
      path: string,
      newPath: string | null = null
    ): Promise<LibraryFile[]> => {
      if (newPath === null) {
        newPath = path;
      }

      const { data } = await octokit.repos.getContent({
        owner: owner,
        repo: repo,
        path: newPath,
      });

      if (!Array.isArray(data)) {
        return [];
      }

      // If it's a directory, recursively fetch its contents
      const subContents = await Promise.all(
        data.map(async (item): Promise<LibraryFile[]> => {
          if (item.type === "file") {
            // console.log(item)
            let regex = new RegExp(path, "g");
            let modifiedPath = item.path.replace(regex, "").substring(1);
            return [{ path: modifiedPath, url: item.download_url ?? "" }];
          } else if (item.type === "dir") {
            const newPath = `${path}/${item.name}`;
            return await fetchContents(path, newPath);
          } else {
            return [];
          }
        })
      );

      return subContents.flat();
    };

    const labels = { manufacturer: manufacturer, model: model };

    try {
      const files = await fetchContents(
        "custom_components/powercalc/data/" + manufacturer + "/" + model
      );
      if (files.length === 0) {
        console.error("No data found", manufacturer, model);
        res.status(404).json({ message: "No download url's found" });
        return;
      }
      logger.info("Data successfully retrieved for %s/%s", manufacturer, model);
      logger.info("Data successfully", { manufacturer: "foo" });
      promDownloadCounter.inc(labels);
      res.json(files);
    } catch (error) {
      logger.error("Model not found");
      res
        .status(404)
        .json({ message: "Model not found %s/%s", manufacturer, model });
    }
  }
);

app.get("/library", cache("1 hour"), async (req: Request, res: Response) => {
  const url =
    "https://raw.githubusercontent.com/bramstroker/homeassistant-powercalc/feat/library-download/custom_components/powercalc/data/library.json";
  logger.info("Fetching library");
  const resp = await fetch(url);
  res.json(await resp.json());
});

app.get("/cache/index", verifyToken, (req, res) => {
  res.json(apicache.getIndex());
});

app.get("/cache/clear", verifyToken, (req, res) => {
  res.json(apicache.clear([]));
});

app.get("/metrics", verifyToken, async (req, res) => {
  res.setHeader("Content-Type", register.contentType);
  res.send(await register.metrics());
});

app.listen(port, () => {
  console.log(`[server]: Server is running at http://localhost:${port}`);
});
