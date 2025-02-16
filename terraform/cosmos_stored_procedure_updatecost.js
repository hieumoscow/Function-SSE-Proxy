function updateAccumulatedCost(counterKey, model, currentCost, startDate, windowDuration, explicitEndDate, quota) {
    var collection = getContext().getCollection();
    var response = getContext().getResponse();
    var docId = model + "_" + counterKey;

    // Validate input parameters
    if (!counterKey || !model) {
        throw new Error("counterKey and model are required parameters");
    }
    if (typeof currentCost !== 'number' || currentCost < 0) {
        throw new Error("currentCost must be a non-negative number");
    }
    if (typeof quota !== 'number' || quota <= 0) {
        throw new Error("quota must be a positive number");
    }

    // Since we're already in the partition for this docId, we can just check if the document exists
    var isAccepted = collection.readDocument(
        collection.getAltLink() + "/docs/" + docId,
        function(err, doc) {
            if (err && err.number !== 404) throw err;

            var now = new Date();
            var nowISO = now.toISOString();

            if (!doc) {
                // Document not found, create new one
                var newDoc = {
                    id: docId,
                    counterKey: counterKey,
                    model: model,
                    accumulatedCost: currentCost,
                    startDate: startDate || nowISO,
                    windowDuration: windowDuration || 2592000, // 30 days in seconds default
                    explicitEndDate: explicitEndDate || null,
                    quota: quota,
                    lastUpdated: nowISO
                };

                var isCreated = collection.createDocument(
                    collection.getSelfLink(),
                    newDoc,
                    function(err, createdDoc) {
                        if (err) throw err;
                        response.setBody(createdDoc);
                    }
                );

                if (!isCreated) throw new Error("Failed to create document");
                return;
            }

            // Document exists, update it
            var start = new Date(doc.startDate || startDate || doc.lastUpdated);
            var end = explicitEndDate ? new Date(explicitEndDate) : 
                     new Date(start.getTime() + (doc.windowDuration || windowDuration) * 1000);

            // If current time is beyond the window, reset the window
            if (now > end) {
                doc.accumulatedCost = currentCost;
                doc.startDate = nowISO;
            } else {
                // Check if adding currentCost would exceed quota
                var newTotal = doc.accumulatedCost + currentCost;
                if (newTotal > quota) {
                    throw new Error(`Adding cost ${currentCost} would exceed quota of ${quota}. Current accumulated cost: ${doc.accumulatedCost}`);
                }
                doc.accumulatedCost = newTotal;
            }

            doc.lastUpdated = nowISO;
            if (windowDuration) doc.windowDuration = windowDuration;
            if (explicitEndDate) doc.explicitEndDate = explicitEndDate;
            doc.quota = quota;
            
            // Update the document
            var isUpdated = collection.replaceDocument(
                doc._self,
                doc,
                function(err, updatedDoc) {
                    if (err) throw err;
                    response.setBody(updatedDoc);
                }
            );

            if (!isUpdated) throw new Error("Failed to update document");
        }
    );

    if (!isAccepted) throw new Error("Failed to read document");
}