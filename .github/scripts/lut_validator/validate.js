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

main();