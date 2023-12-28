/// <reference path="../pb_data/types.d.ts" />
migrate((db) => {
  const collection = new Collection({
    "id": "bf49rbpqbz1aeij",
    "created": "2023-12-20 13:46:11.278Z",
    "updated": "2023-12-20 13:46:11.278Z",
    "name": "stats_played",
    "type": "base",
    "system": false,
    "schema": [
      {
        "system": false,
        "id": "eauamyfw",
        "name": "uri",
        "type": "text",
        "required": false,
        "presentable": false,
        "unique": false,
        "options": {
          "min": null,
          "max": null,
          "pattern": ""
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
  const collection = dao.findCollectionByNameOrId("bf49rbpqbz1aeij");

  return dao.deleteCollection(collection);
})
