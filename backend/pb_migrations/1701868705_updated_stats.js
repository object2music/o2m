migrate((db) => {
  const dao = new Dao(db)
  const collection = dao.findCollectionByNameOrId("iv189k3by303uqw")

  // add
  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "zv1aaivu",
    "name": "flow",
    "type": "relation",
    "required": false,
    "unique": false,
    "options": {
      "collectionId": "kljaijw0sdn49jw",
      "cascadeDelete": false,
      "minSelect": null,
      "maxSelect": null,
      "displayFields": []
    }
  }))

  return dao.saveCollection(collection)
}, (db) => {
  const dao = new Dao(db)
  const collection = dao.findCollectionByNameOrId("iv189k3by303uqw")

  // remove
  collection.schema.removeField("zv1aaivu")

  return dao.saveCollection(collection)
})
