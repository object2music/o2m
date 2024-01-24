migrate((db) => {
  const dao = new Dao(db)
  const collection = dao.findCollectionByNameOrId("85jzekh9i9xp3in")

  // add
  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "rxfsjz4v",
    "name": "favorite",
    "type": "bool",
    "required": false,
    "unique": false,
    "options": {}
  }))

  // add
  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "lfih6upu",
    "name": "public",
    "type": "bool",
    "required": false,
    "unique": false,
    "options": {}
  }))

  return dao.saveCollection(collection)
}, (db) => {
  const dao = new Dao(db)
  const collection = dao.findCollectionByNameOrId("85jzekh9i9xp3in")

  // remove
  collection.schema.removeField("rxfsjz4v")

  // remove
  collection.schema.removeField("lfih6upu")

  return dao.saveCollection(collection)
})
