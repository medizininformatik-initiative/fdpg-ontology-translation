# Generating translations of ValueSets

## How it works

```bash 
python translate.py --deepl --package_cache fhir-package-cache
```

1. By starting the script the ``ValueSetManager.py`` collects all valuesets found in the specified source folder
   and expands all which are not already present in the cache using the server and caches them into a folder on disk.
   Expansion can take quite some time => caching is useful.
2. With all valuesets expanded the ``Translator.py`` collects all codes and sorts them by the following key (system,
   version)
   into a dictionary
3. All existing **FDPG** supplements get downloaded and already existing translations get reused for matching codes,
   where the
   original display did not change, across all versions of a codesystem.
4. ``Translator`` uses the specified ``TranslationEngine`` (deepl, dry_run, llm - coming soon) to translate the
   remaining
   codes
   which were not covered by the supplements
    - In all cases the language is guessed once per codesystem by the predefined ``codesystem to language`` mapping or
      the local python module "``lingua``"
    - ``DeeplTranslationEngine``: uses a ``.detected_source_lang`` to confirm the guess and carries on translating if
      true. Else DeepL’s detected language replaces the guess for the rest of the translation.
    - ``DryRunTranslationEngine``: assumes the guessed language is correct and only counts the characters
5. Translated codesystems get exported to the output folder by (system, version) as supplements

## Using this script

### Before executing the script

- install dependencies
  ````bash
    pip install -r requirements.txt
  ````
- configure project .env
    - follow the [.env.example](.env.example) and the [env param table](#script-env-params) below

### Script I/O

There are two ways to provide the script with the valuesets to be translated. At least one must be provided.

1. by ``--package_cache <package-cache-folder>`` which takes a folder with the structure as how the package_manager from
   the ontology-generator would provide. It can be copy-pasted.
2. by ```--input_folder <input-valuesets>``` by simply dumping valuesets to be translated into the input folder

The translated files will be found in the specified folder ```--target_folder <output-folder>``` (default:
"code-systems")

### Script params

| Parameter       | Explanation                                                                               | Example - default |
|-----------------|-------------------------------------------------------------------------------------------|:------------------|
| --target_folder | folder to store the result                                                                | "code-systems"    |
| --deepl         | Choose to translate with deepl translation engine - only works when api key is provided   |                   |
| --dry_run       | Default behaviour. Do not translate, only count number of characters to be translated.    |                   |
| --package_cache | input valuesets structured as the package-manager of the ontology-generator would produce |                   |
| --input_folder  | input folder of valuesets                                                                 | None              |

### Script .env params

- see .env.example for details

| Parameter                 | Explanation                                                          | Example                              |
|---------------------------|----------------------------------------------------------------------|--------------------------------------|
| DEEPL_API_KEY             | deepl api key                                                        |                                      |
| TERMINOLOGY_SERVER        | fhir endpoint of termserver                                          | https://public-test.example.de/fhir/ |
| BACKUP_TERMINOLOGY_SERVER | backup terminology server - asked when the main server has no result |                                      |
| SERVER_CERTIFICATE        | path to .pem server certificate                                      |                                      |
| PRIVATE_KEY               | path to .key private key for server certificate                      |                                      |
| LOG_LEVEL                 | log level                                                            | info                                 |













