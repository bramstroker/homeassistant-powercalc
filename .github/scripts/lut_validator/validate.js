const csval = require('csval');
const readdirp = require('readdirp');
const { ungzip } = require('node-gzip');
const fs = require('fs');
const { exit } = require('process');
const path = require('path');

const main = async () => {
  const dataDirectory = path.join(__dirname, '../../../custom_components/powercalc/data')
  let hasError = false
  for await (const file of readdirp(dataDirectory, {fileFilter: '*.csv.gz'})) {
    const colorMode = file.basename.substring(0, file.basename.indexOf('.csv.gz'))

    console.log('Checking ' + file.path)
    const gzipped = fs.readFileSync(file.fullPath)
    const csvBuffer = await ungzip(gzipped)
    const parsed = await csval.parseCsv(csvBuffer.toString());
    const rules = await csval.readRules(path.join(__dirname, 'rules/' + colorMode + '.json'));
    try {
      await csval.validate(parsed, rules)
      validateMaxBrightness(parsed)
    } catch (ex) {
      console.log('Invalid')
      console.log(ex)
      hasError = true
      continue;
    }
    console.log('Valid')
  }

  if (hasError) {
    exit(1)
  }
};

const validateMaxBrightness = (parsedCsv) => {
  brightnessValues = parsedCsv['data'].map((row) => row['bri'])
  maxBrightness = Math.max(...brightnessValues)
  if (maxBrightness < 250) {
    throw new Error('Max brightness level is less than 255. Measurements probably not finished completely')
  }
}

main();