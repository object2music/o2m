migrate((db) => {
  const collection = new Collection({
    "id": "85jzekh9i9xp3in",
    "created": "2023-10-30 15:22:08.469Z",
    "updated": "2023-10-30 15:22:08.469Z",
    "name": "boxes",
    "type": "base",
    "system": false,
    "schema": [
      {
        "system": false,
        "id": "mujy0yko",
        "name": "name",
        "type": "text",
        "required": false,
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
  const collection = dao.findCollectionByNameOrId("85jzekh9i9xp3in");

  return dao.deleteCollection(collection);
})
