migrate((db) => {
  const dao = new Dao(db)
  const collection = dao.findCollectionByNameOrId("85jzekh9i9xp3in")

  // add
  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "7loawifo",
    "name": "flow",
    "type": "relation",
    "required": false,
    "unique": false,
    "options": {
      "collectionId": "kljaijw0sdn49jw",
      "cascadeDelete": false,
      "minSelect": null,
      "maxSelect": 1,
      "displayFields": []
    }
  }))

  return dao.saveCollection(collection)
}, (db) => {
  const dao = new Dao(db)
  const collection = dao.findCollectionByNameOrId("85jzekh9i9xp3in")

  // remove
  collection.schema.removeField("7loawifo")

  return dao.saveCollection(collection)
})
