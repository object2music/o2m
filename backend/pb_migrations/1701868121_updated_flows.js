migrate((db) => {
  const dao = new Dao(db)
  const collection = dao.findCollectionByNameOrId("kljaijw0sdn49jw")

  // remove
  collection.schema.removeField("v0zutziy")

  // add
  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "0a3ujpzx",
    "name": "sort",
    "type": "select",
    "required": false,
    "unique": false,
    "options": {
      "maxSelect": 1,
      "values": [
        "shuffle",
        "desc",
        "asc"
      ]
    }
  }))

  return dao.saveCollection(collection)
}, (db) => {
  const dao = new Dao(db)
  const collection = dao.findCollectionByNameOrId("kljaijw0sdn49jw")

  // add
  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "v0zutziy",
    "name": "sort",
    "type": "text",
    "required": false,
    "unique": false,
    "options": {
      "min": null,
      "max": null,
      "pattern": ""
    }
  }))

  // remove
  collection.schema.removeField("0a3ujpzx")

  return dao.saveCollection(collection)
})
