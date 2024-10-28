# Generating translations of ValueSets

## Using this script
### Before executing the script
- prepare the url of your fhir term server
- get the certificate
  - server certificate
  - key (**the key must be unencrypted!**)
     ````bash
    openssl rsa -in client_cert/fdpg.key -out client_cert/fdpg_unencrypted.key
    ````
- get a deeplAPI key and install module called '*deepl*'
  ````bash
    pip install deepl
  ````
- ValueSets.json
  - generate the valuesets.json based on a folder stored locally by executing the script: generate_default_value_set_list.py
    - specify the folder using the ***--value_sets_folder*** argument
    - if you want automatic language detection use ***--lang_detection***
  - or prepare the json file yourself, which holds pairs of (urls,source_language) like in the example below:
     ````json
    [
      {
        "url": "https://www.medizininformatik-initiative.de/fhir/core/modul-person/ValueSet/Vitalstatus",
        "source_lang" : "de"
      },{
        "url": "value-sets/Vitalstatus.json",
        "source_lang" : "de"
      },
      {
       "url": "value-sets/administrative-gender.json",
        "source_lang" : "en"
      }
    ] 
     ````
### After executing the script
The translated files will be found in the specified folder

### Discussing parameters

| Parameter            | Explanation                                                        | Value                                       | Example                                                  |
|----------------------|--------------------------------------------------------------------|:--------------------------------------------|:---------------------------------------------------------|
| --terminology_server | fhir term server url                                               | string                                      | ex: https://public-test.mii-termserv.de/fhir/            |
| --server_certificate | certificate for the server                                         | string (filePath to .pem)                   | client_cert/fdpg.pem                                     |
| --private_key        | certificate key                                                    | string (filePath to ***unencrypted!***.key) | client_cert/fdpg_unencrypted.key                         |
| --deepl_api_key      | Deepl apiKey                                                       | string                                      |                                                          |
| --value_sets         | files to be translated                                             | string (filePath to .json)                  | follow the example above or test with **ValueSets.json** |
| --target_folder      | folder to store the result                                         | string (folder path)                        | code-systems                                             |
| --log_level          | notset,debug,info,warning,error,critical                           |                                             |                                                          |
| --batch_size         | nr  of elements sent simultaneously                                | int                                         | 5                                                        |
| --dry_run            | Do not translate, only count number of characters to be translated | store_true                                  |                                                          |


### Using local files
Just specify local files in your "value_sets" .json file. 
When there are only local files the server_certificate and private_key become oboslete

You can mix local files and urls in on json file
