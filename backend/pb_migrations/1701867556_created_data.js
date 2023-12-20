migrate((db) => {
  const collection = new Collection({
    "id": "afv21ixeixtla5h",
    "created": "2023-12-06 12:59:16.662Z",
    "updated": "2023-12-06 12:59:16.662Z",
    "name": "data",
    "type": "base",
    "system": false,
    "schema": [
      {
        "system": false,
        "id": "muq6biqb",
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
        "id": "13gmuygt",
        "name": "type",
        "type": "select",
        "required": false,
        "unique": false,
        "options": {
          "maxSelect": 1,
          "values": [
            "podcast",
            "track",
            "playlist",
            "album",
            "youtube",
            "radio"
          ]
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
  const collection = dao.findCollectionByNameOrId("afv21ixeixtla5h");

  return dao.deleteCollection(collection);
})
