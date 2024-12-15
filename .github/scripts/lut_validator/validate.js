import csval from 'csval';
import readdirp from 'readdirp';
import zlib from 'zlib';
import fs from 'fs';
import process from 'process';
import path from 'path';
import chalk from 'chalk';
import { fileURLToPath } from 'url';
import { dirname } from 'path';
import util from 'util';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const validColorModeCombinations = [
    'color_temp,hs',
    'color_temp',
    'hs',
    'brightness',
    //The entries below are not really valid combinations according to HA docs, but some core integrations in HA supply this (for example TP-Link)
    'brightness,hs',
    'brightness,color_temp,hs',
    'brightness,color_temp'
]

const pattern = /(\/|^)(hs|color_temp|brightness)\.csv\.gz$/;
const main = async () => {
    const dataDirectory = path.join(__dirname, '../../../profile_library')
    let errors = []
    for await (const model_dir of readdirp(dataDirectory, {depth: 2, type: 'directories'})) {
        if (!model_dir.path.includes('/')) {
            continue
        }
        console.log('Processing model directory ' + model_dir.path)
        let colorModes = new Set()
        for await (const file of readdirp(model_dir.fullPath, {fileFilter: '*.csv.gz'})) {
            if (!pattern.test(file.fullPath)) {
                continue
            }
            const colorMode = file.basename.substring(0, file.basename.indexOf('.csv.gz'))
            colorModes.add(colorMode)
            console.log('Checking ' + file.path)
            const gzipped = fs.readFileSync(file.fullPath)
            const csvBuffer = await util.promisify(zlib.gunzip)(gzipped)
            const parsed = await csval.parseCsv(csvBuffer.toString());
            const rules = await csval.readRules(path.join(__dirname, 'rules/' + colorMode + '.json'));
            try {
                await csval.validate(parsed, rules)
                validateMaxBrightness(parsed)
            } catch (ex) {
                console.log(chalk.red('Invalid'))
                console.log(chalk.red(ex.message))
                errors.push({model: model_dir.path, colorMode: colorMode, message: ex.message})
                continue;
            }
            console.log(chalk.green('Valid'))
        }

        if (colorModes.size > 0) {
            try {
                validateColorModes(colorModes)
            } catch (ex) {
                console.log(chalk.red(ex))
                errors.push({model: model_dir.path, colorMode: colorMode, message: ex.message})
            }
        }
    }

    if (errors.length) {
        console.log('There were errors:')
        for (let i = 0; i < errors.length; i++) {
            const error = errors[i]
            console.log(chalk.red(error.model + ' - ' + error.colorMode + ': ' + error.message))
        }
        process.exit(1)
    }
};

const validateMaxBrightness = (parsedCsv) => {
    const brightnessValues = parsedCsv['data'].map((row) => row['bri'])
    const maxBrightness = Math.max(...brightnessValues)
    if (maxBrightness < 250) {
        throw new Error('Max brightness level ' + maxBrightness + ' is less than 250. Measurements probably not finished completely')
    }
}

const validateColorModes = (colorModes) => {
    if (validColorModeCombinations.indexOf([...colorModes].join(',')) === -1) {
        throw new Error('Invalid color mode combination ' + [...colorModes].join(','))
    }
}

main();
