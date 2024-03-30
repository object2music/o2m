migrate((db) => {
  const dao = new Dao(db)
  const collection = dao.findCollectionByNameOrId("kljaijw0sdn49jw")

  // remove
  collection.schema.removeField("0oyar6ao")

  return dao.saveCollection(collection)
}, (db) => {
  const dao = new Dao(db)
  const collection = dao.findCollectionByNameOrId("kljaijw0sdn49jw")

  // add
  collection.schema.addField(new SchemaField({
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
  }))

  return dao.saveCollection(collection)
})
