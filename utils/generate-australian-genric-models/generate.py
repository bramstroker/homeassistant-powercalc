import urllib.request
import csv

categories = {
	"28": "Refrigerator/Freezer",
	# "32": "Televisions",
	# "33": "Set Top Boxes",
	# "34": "Linear Fluorescent Lamps",
	# "35": "Clothes Dryers",
	# "37": "Refrigerated Cabinets",
	# "38": "Distribution Transformers",
	# "39": "ELV Lighting Converter/Transformer",
	# "40": "Incandescent Lamps",
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
for key in categories.keys():
	url = "https://reg.energyrating.gov.au/comparator/product_types/" + key + "/search/?expired_products=on&export_format=csv"

	response = urllib.request.urlopen(url)
	lines = [l.decode('utf-8') for l in response.readlines()]
	for row in csv.reader(lines):
		print(row)
