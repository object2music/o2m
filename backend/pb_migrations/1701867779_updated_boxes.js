migrate((db) => {
  const dao = new Dao(db)
  const collection = dao.findCollectionByNameOrId("85jzekh9i9xp3in")

  // add
  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "ih6wfxdr",
    "name": "read_count",
    "type": "number",
    "required": false,
    "unique": false,
    "options": {
      "min": null,
      "max": null
    }
  }))

  // add
  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "toj2izuh",
    "name": "last_read_date",
    "type": "date",
    "required": false,
    "unique": false,
    "options": {
      "min": "",
      "max": ""
    }
  }))

  return dao.saveCollection(collection)
}, (db) => {
  const dao = new Dao(db)
  const collection = dao.findCollectionByNameOrId("85jzekh9i9xp3in")

  // remove
  collection.schema.removeField("ih6wfxdr")

  // remove
  collection.schema.removeField("toj2izuh")

  return dao.saveCollection(collection)
})
