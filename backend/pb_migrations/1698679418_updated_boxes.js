migrate((db) => {
  const dao = new Dao(db)
  const collection = dao.findCollectionByNameOrId("85jzekh9i9xp3in")

  // add
  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "6ts4xos9",
    "name": "image",
    "type": "file",
    "required": false,
    "unique": false,
    "options": {
      "maxSelect": 1,
      "maxSize": 5242880,
      "mimeTypes": [],
      "thumbs": [],
      "protected": false
    }
  }))

  return dao.saveCollection(collection)
}, (db) => {
  const dao = new Dao(db)
  const collection = dao.findCollectionByNameOrId("85jzekh9i9xp3in")

  // remove
  collection.schema.removeField("6ts4xos9")

  return dao.saveCollection(collection)
})
