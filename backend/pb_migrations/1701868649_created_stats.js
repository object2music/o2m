migrate((db) => {
  const collection = new Collection({
    "id": "iv189k3by303uqw",
    "created": "2023-12-06 13:17:29.935Z",
    "updated": "2023-12-06 13:17:29.935Z",
    "name": "stats",
    "type": "base",
    "system": false,
    "schema": [
      {
        "system": false,
        "id": "1fn3ea5y",
        "name": "uri",
        "type": "text",
        "required": false,
        "unique": false,
        "options": {
          "min": null,
          "max": null,
          "pattern": ""
        }
      },
      {
        "system": false,
        "id": "w29jr4du",
        "name": "last_read_date",
        "type": "date",
        "required": false,
        "unique": false,
        "options": {
          "min": "",
          "max": ""
        }
      },
      {
        "system": false,
        "id": "uxdadhjc",
        "name": "read_position",
        "type": "number",
        "required": false,
        "unique": false,
        "options": {
          "min": null,
          "max": null
        }
      },
      {
        "system": false,
        "id": "mvgyfjtm",
        "name": "finished_score",
        "type": "number",
        "required": false,
        "unique": false,
        "options": {
          "min": null,
          "max": null
        }
      },
      {
        "system": false,
        "id": "iasgrnmk",
        "name": "count_score",
        "type": "number",
        "required": false,
        "unique": false,
        "options": {
          "min": null,
          "max": null
        }
      },
      {
        "system": false,
        "id": "bwskj8qe",
        "name": "skipped_score",
        "type": "number",
        "required": false,
        "unique": false,
        "options": {
          "min": null,
          "max": null
        }
      },
      {
        "system": false,
        "id": "t8pvhsfj",
        "name": "day_time_average",
        "type": "number",
        "required": false,
        "unique": false,
        "options": {
          "min": null,
          "max": null
        }
      }
    ],
    "indexes": [],
    "listRule": null,
    "viewRule": null,
    "createRule": null,
    "updateRule": null,
    "deleteRule": null,
    "options": {}
  });

  return Dao(db).saveCollection(collection);
}, (db) => {
  const dao = new Dao(db);
  const collection = dao.findCollectionByNameOrId("iv189k3by303uqw");

  return dao.deleteCollection(collection);
})
