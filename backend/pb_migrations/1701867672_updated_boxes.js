migrate((db) => {
  const dao = new Dao(db)
  const collection = dao.findCollectionByNameOrId("85jzekh9i9xp3in")

  // add
  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "n1eodhh1",
    "name": "contents",
    "type": "relation",
    "required": false,
    "unique": false,
    "options": {
      "collectionId": "afv21ixeixtla5h",
      "cascadeDelete": false,
      "minSelect": null,
      "maxSelect": null,
      "displayFields": []
    }
  }))

  return dao.saveCollection(collection)
}, (db) => {
  const dao = new Dao(db)
  const collection = dao.findCollectionByNameOrId("85jzekh9i9xp3in")

  // remove
  collection.schema.removeField("n1eodhh1")

  return dao.saveCollection(collection)
})
