migrate((db) => {
  const collection = new Collection({
    "id": "kljaijw0sdn49jw",
    "created": "2023-12-06 13:04:20.646Z",
    "updated": "2023-12-06 13:04:20.646Z",
    "name": "flows",
    "type": "base",
    "system": false,
    "schema": [
      {
        "system": false,
        "id": "0oyar6ao",
        "name": "option_type",
        "type": "select",
        "required": false,
        "unique": false,
        "options": {
          "maxSelect": 1,
          "values": [
            "library",
            "new",
            "incoming",
            "favorites",
            "hidden",
            "trash"
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
  const collection = dao.findCollectionByNameOrId("kljaijw0sdn49jw");

  return dao.deleteCollection(collection);
})
