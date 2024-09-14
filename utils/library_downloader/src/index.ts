import express, { Express, Request, Response, NextFunction } from "express";
import dotenv from "dotenv";
import cors from "cors";
import apicache from "apicache";
import { Octokit } from "@octokit/rest";
import pino from "pino";
import promClient from "prom-client";
import promBundle from "express-prom-bundle";

dotenv.config();

const port = process.env.PORT || 3000;
const githubToken = process.env.GITHUB_TOKEN;
const bearerToken = process.env.BEARER_TOKEN;
const logLevel = process.env.LOG_LEVEL || 'info'
const defaultOwner = "bramstroker";
const defaultRepo = "homeassistant-powercalc";
const defaultPath = "profile_library"
const defaultBranch = process.env.REPO_BRANCH || "master"

const app: Express = express();
const logger = pino(
    {
        level: logLevel
    }
);
const collectDefaultMetrics = promClient.collectDefaultMetrics;
collectDefaultMetrics();

export interface LibraryFile {
  path: string;
  url: string;
}

export interface Repository {
  owner: string;
  repo: string;
  path: string;
  branch: string;
}

let promDownloadCounter = new promClient.Counter({
  name: "powercalc_download",
  help: "Number of downloads for a profile",
  labelNames: ["manufacturer", "model"] as const,
});
promClient.register.registerMetric(promDownloadCounter);

const metricsMiddleware = promBundle({
    autoregister: false,
    includeMethod: true,
    includePath: true,
    includeStatusCode: true,
    includeUp: true,
});
app.use(metricsMiddleware)

app.use(cors())

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
  logger.debug("Request token: %s", bearerToken)
  logger.debug("Env token: %s", token)
  if (token != bearerToken) {
    res.status(403).send("Invalid token.");
    return;
  }
  next();
};

const getRepository: (req: Request) => Repository = (req: Request) => {
  const repositoryHeader = req.header("X-Powercalc-Repository")
    if (repositoryHeader) {
        const parts = repositoryHeader.split("/")

        return {
            owner: parts[0],
            repo: parts[1],
            branch: parts[2],
            path: parts.slice(3).join('/')
        }
    }
    return { owner: defaultOwner, repo: defaultRepo, path: defaultPath, branch: defaultBranch }
};

const getRawBaseUri: (repository: Repository) => string = (repository: Repository) => {
  return `https://raw.githubusercontent.com/${repository.owner}/${repository.repo}/${repository.branch}/${repository.path}`
}

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

    const repository = getRepository(req)
    logger.debug("Repository: %s/%s/%s", repository.owner, repository.repo, repository.path)

    const fetchContents = async (
      path: string,
      newPath: string | null = null,
    ): Promise<LibraryFile[]> => {
      if (newPath === null) {
        newPath = path;
      }

      let { data } = await octokit.repos.getContent({
        owner: repository.owner,
        repo: repository.repo,
        path: newPath,
        ref: repository.branch
      });

      if (!Array.isArray(data)) {
        data = [data]
      }

      const subContents = await Promise.all(
        data.map(async (item): Promise<LibraryFile[]> => {
          logger.debug(item.type)
          if (item.type === "file") {
            if (!item.path.startsWith(path)) {
                throw new Error("No match found.");
            }
            const modifiedPath = item.path.substring(path.length + 1);
            return [{ path: modifiedPath, url: item.download_url ?? "" }];
          } else if (item.type === "symlink") {
            const target = item.target
            return await fetchContents(target.replace("../", repository.path + "/"))
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
      const libraryPath = repository.path;
      const pattern = req.query.includePlots ? '.*' : '^(?!.*\.png$).*'
      let files = await fetchContents(
        libraryPath + "/" + manufacturer + "/" + model
      );
      files = files.filter((item) => new RegExp(pattern).test(item.path))
      if (files.length === 0) {
        logger.error("No data found for: %s/%s", manufacturer, model);
        res.status(404).json({ message: "No download url's found" });
        return;
      }
      logger.info("Data successfully retrieved for %s/%s", manufacturer, model);
      promDownloadCounter.inc(labels);
      res.json(files);
    } catch (error) {
      logger.error("Error fetching data: %s", error);
      logger.error("Model not found %s/%s", manufacturer, model);
      res
        .status(404)
        .json({ message: "Model not found %s/%s", manufacturer, model });
    }
  }
);

app.get("/profile/:manufacturer/:model", cache("1 hour"), async (req: Request, res: Response) => {
  const repository = getRepository(req)

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

    const url = getRawBaseUri(repository) + '/' + manufacturer + '/' + model + '/model.json';
    logger.debug("Fetching profile: %s/%s", manufacturer, model);

    try {
      const resp = await fetch(url);
      res.set('Cache-Control', 'public, max-age=3600');
      res.json(await resp.json());
    } catch (error) {
      logger.error("Error fetching profile: %s", error);
      res.status(404).json({ message: "Could not find profile" });
    }
});

app.get("/library", cache("1 hour"), async (req: Request, res: Response) => {
  const repository = getRepository(req)
  const url = getRawBaseUri(repository) + '/library.json';
  console.log(url)
  logger.info("Fetching library");
  try {
    const resp = await fetch(url);
    res.set('Cache-Control', 'public, max-age=3600');
    res.json(await resp.json());
  } catch (error) {
    logger.error("Error fetching library: %s", error);
    res.status(500).json({ message: "Error fetching library" });
  }
});

app.get("/cache/index", verifyToken, (req, res) => {
  res.json(apicache.getIndex());
});

app.get("/cache/flush", verifyToken, (req, res) => {
  res.json(apicache.clear(''));
});

app.get("/metrics", verifyToken, async (req, res) => {
  res.setHeader("Content-Type", promClient.register.contentType);
  res.send(await promClient.register.metrics());
});

app.listen(port, () => {
  console.log(`[server]: Server is running at http://localhost:${port}`);
});
