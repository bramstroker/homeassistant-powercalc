import urllib.request
import csv

categories = {
	# "28": "Refrigerator/Freezer",
	# "32": "Televisions",
	# "33": "Set Top Boxes",
	# "34": "Linear Fluorescent Lamps",
	# "35": "Clothes Dryers",
	# "37": "Refrigerated Cabinets",
	# "38": "Distribution Transformers",
	# "39": "ELV Lighting Converter/Transformer",
	"40": "Incandescent Lamps",
	# "41": "Dishwashers",
	# "49": "Clothes Washers",
	# "51": "Ballasts",
	# "54": "Electric Motors",
	# "55": "External Power Supply",
	# "58": "Hot Water Heaters (Electric)",
	# "59": "Chillers",
	# "60": "Close Control Air Conditioners",
	# "61": "Compact Fluorescent Lamps",
	# "62": "Hot Water Heaters (Gas)",
	# "64": "Air Conditioners",
	# "73": "Computers",
	# "74": "Computer Monitors",
	# "83": "Pool Pump"
}

class IncandescentLampMapper:
	def __init__(self, row):
		# "Submit_ID",
		self.brand = row[1] # "Brand",
		self.model_number = row[2] # "Model_No",
		# "Family Name",
		# "SoldIn",
		# "Country",
		# "Sing_or_fam",
		self.watts = row[7] # "nom_lamp_power", # Lamp Watts
		# "avg_meas_lum_flux",
		# "median_lamp_life",
		# "lumen_maintenance"
		# "avg_meas_efficacy",
		# "inputvolt_min",
		# "inputvolt_max",
		# "ExpDate",
		# "GrandDate",
		# "SubmitStatus",
		# "Product Class",
		# "Availability Status",
		# "Product Website", 
		# "Representative Brand URL"
		# "Lamp Light Output (Lumens)",
		# "Lamp Type",
		self.measure_description = row[23] # "What test standard was used"

	def as_model_json(self):
		return {
		   "brand": self.brand,
		   "model_number": self.model_number,
		   "measure_description": self.measure_description,
		   "measure": "manual",
		   "device_type": "light",
		   "supported_modes": ["fixed"]
		}

mappers = {
	"Incandescent Lamps": IncandescentLampMapper
}

# TODO: Each of these is a different format
# TODO: Cache?
# TODO: Heading to model.json mappings
for key, label in categories.items():
	url = "https://reg.energyrating.gov.au/comparator/product_types/" + key + "/search/?expired_products=on&export_format=csv"

	response = urllib.request.urlopen(url)
	lines = [l.decode('utf-8') for l in response.readlines()]
	for row in csv.reader(lines):
		mapper = mappers[label](row)
		print(mapper.as_model_json())
