


import json


middleman_config = dict(
    listen_port=9000
)


with open('./middleman_config.json', 'w') as fd:
    json.dump(middleman_config, fd, indent=2)
