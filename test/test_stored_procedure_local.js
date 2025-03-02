const fs = require('fs');

// Mock Cosmos DB collection
class MockCollection {
    constructor() {
        this.docs = new Map();
        this.baseLink = "/dbs/testdb/colls/testcoll";
    }

    readDocument(link, callback) {
        try {
            // Handle both full link format and direct docId
            const docId = link.includes('/docs/') ? link.split('/docs/')[1] : link;
            if (this.docs.has(docId)) {
                const doc = this.docs.get(docId);
                // Ensure _self is set
                if (!doc._self) {
                    doc._self = `${this.baseLink}/docs/${docId}`;
                }
                callback(null, doc);
            } else {
                callback({ number: 404 }, null);
            }
            return true; // isAccepted should be true even for 404 cases
        } catch (error) {
            callback(error, null);
            return false;
        }
    }

    createDocument(selfLink, doc, callback) {
        try {
            // Add _self property to the document
            doc._self = `${this.baseLink}/docs/${doc.id}`;
            this.docs.set(doc.id, doc);
            callback(null, doc);
            return true;
        } catch (error) {
            callback(error, null);
            return false;
        }
    }

    replaceDocument(link, doc, callback) {
        try {
            const docId = doc.id;
            // Ensure _self is preserved
            doc._self = `${this.baseLink}/docs/${docId}`;
            this.docs.set(docId, doc);
            callback(null, doc);
            return true;
        } catch (error) {
            callback(error, null);
            return false;
        }
    }

    getAltLink() {
        return this.baseLink;
    }

    getSelfLink() {
        return this.baseLink;
    }
}

// Mock Cosmos DB context
class MockContext {
    constructor() {
        this.collection = new MockCollection();
        this.response = {
            body: null,
            setBody: function(body) {
                this.body = body;
            }
        };
    }

    getCollection() {
        return this.collection;
    }

    getResponse() {
        return this.response;
    }
}

// Test framework
class TestRunner {
    constructor(spPath) {
        this.spContent = fs.readFileSync(spPath, 'utf8');
        this.tests = new Map();
        this.results = {
            passed: 0,
            failed: 0,
            failedTests: []
        };
    }

    createStoredProcedure(context) {
        const getContext = () => context;
        const module = { exports: {} };
        const fn = new Function('module', 'getContext', this.spContent + '\nmodule.exports = updateAccumulatedCost;');
        fn(module, getContext);
        return module.exports;
    }

    addTest(name, testFn) {
        this.tests.set(name, testFn);
    }

    async runTests() {
        console.log('Running tests for updateAccumulatedCost stored procedure...\n');
        
        const GREEN_CHECK = '\x1b[32m✓\x1b[0m';
        const RED_X = '\x1b[31m✗\x1b[0m';
        
        for (const [name, testFn] of this.tests) {
            console.log(`Running test: ${name}`);
            try {
                const context = new MockContext();
                const sp = this.createStoredProcedure(context);
                await testFn(sp, context);
                console.log(`${GREEN_CHECK} Test passed\n`);
                this.results.passed++;
            } catch (error) {
                if (error.expected) {
                    console.log(`${GREEN_CHECK} Test passed: ${error.message}\n`);
                    this.results.passed++;
                } else {
                    console.error(`${RED_X} Test failed: ${error.message}\n`);
                    this.results.failed++;
                    this.results.failedTests.push({
                        name: name,
                        error: error.message
                    });
                }
            }
        }

        // Print summary at the end
        console.log('\n=== Test Summary ===');
        console.log(`Total Tests: ${this.tests.size}`);
        console.log(`${GREEN_CHECK} Passed: ${this.results.passed}`);
        if (this.results.failed > 0) {
            console.log(`${RED_X} Failed: ${this.results.failed}`);
            console.log('\nFailed Tests:');
            this.results.failedTests.forEach(failure => {
                console.log(`${RED_X} ${failure.name}: ${failure.error}`);
            });
            throw new Error(`${this.results.failed} test(s) failed`);
        }
    }
}

// Helper functions
function assertDeepEqual(actual, expected, message) {
    const actualStr = JSON.stringify(actual);
    const expectedStr = JSON.stringify(expected);
    if (actualStr !== expectedStr) {
        throw new Error(`${message}\nExpected: ${expectedStr}\nActual: ${actualStr}`);
    }
}

function createExpectedError(message) {
    const error = new Error(message);
    error.expected = true;
    return error;
}

// Test cases
const runner = new TestRunner('../terraform/cosmos_stored_procedure_updatecost.js');

// Helper function to log parameters
function logTestParams(testName, params) {
    console.log('\n=== Test:', testName, '===');
    console.log(JSON.stringify(params, null, 2));
}

/**
 * Test Suite: Document Creation
 */
runner.addTest('Create new document with minimal parameters', async (sp, context) => {
    const now = new Date();
    const params = {
        counterKey: 'test-key-1',
        model: 'gpt-4',
        currentCost: 10.5,
        quota: 100
    };
    logTestParams('Minimal Parameters', params);
    
    sp(params.counterKey, params.model, params.currentCost, null, null, null, params.quota);
    const result = context.getResponse().body;
    assertDeepEqual(result.accumulatedCost, params.currentCost, 'Initial cost not set correctly');
    assertDeepEqual(result.renewalPeriod, null, 'Renewal period should be null');
});

runner.addTest('Create new document with all parameters', async (sp, context) => {
    const now = new Date();
    const params = {
        counterKey: 'test-key-2',
        model: 'gpt-4',
        currentCost: 10.5,
        startDate: now.toISOString(),
        renewalPeriod: 86400, // 1 day in seconds
        endDate: new Date(now.getTime() + 86400000).toISOString(),
        quota: 100
    };
    logTestParams('All Parameters', params);
    
    sp(params.counterKey, params.model, params.currentCost,
        params.startDate, params.renewalPeriod, params.endDate, params.quota);
    const result = context.getResponse().body;
    assertDeepEqual(result.accumulatedCost, params.currentCost, 'Initial cost not set correctly');
    assertDeepEqual(result.startDate, params.startDate, 'Start date not set correctly');
    assertDeepEqual(result.renewalPeriod, params.renewalPeriod, 'Renewal period not set correctly');
    assertDeepEqual(result.endDate, params.endDate, 'End date not set correctly');
});

/**
 * Test Suite: Renewal Period
 */
runner.addTest('Reset accumulated cost at renewal period', async (sp, context) => {
    const params = {
        counterKey: 'test-key-3',
        model: 'gpt-4',
        costs: {
            initial: 40.0,
            additional: 30.0
        },
        startDate: '2024-01-01T00:00:00Z',
        renewalPeriod: 86400, // 1 day in seconds
        quota: 100,
        times: {
            initial: '2024-01-01T12:00:00Z',      // Within first period
            beforeRenewal: '2024-01-01T23:59:59Z', // Just before renewal
            atRenewal: '2024-01-02T00:00:00Z'      // Exactly at renewal time
        }
    };
    logTestParams('Renewal Period', params);
    
    const originalDate = global.Date;
    const mockDate = (dateString) => {
        global.Date = class extends Date {
            constructor() {
                super();
                return new originalDate(dateString);
            }
            static now() {
                return new originalDate(dateString).getTime();
            }
        };
    };
    
    try {
        // 1. Initial cost within first period - SET START DATE
        mockDate(params.times.initial);
        sp(params.counterKey, params.model, params.costs.initial,
            params.startDate, params.renewalPeriod, null, params.quota);
        let result = context.getResponse().body;
        assertDeepEqual(result.accumulatedCost, params.costs.initial,
            'Initial cost should be set');
        
        // 2. Additional cost before renewal (should accumulate)
        mockDate(params.times.beforeRenewal);
        sp(params.counterKey, params.model, params.costs.additional,
            params.startDate, params.renewalPeriod, null, params.quota);
        result = context.getResponse().body;
        assertDeepEqual(result.accumulatedCost, params.costs.initial + params.costs.additional,
            'Cost should accumulate within the same period');
            
        // 3. At renewal time (should reset to 0)
        mockDate(params.times.atRenewal);
        sp(params.counterKey, params.model, 0,
            params.startDate, params.renewalPeriod, null, params.quota);
        result = context.getResponse().body;
        assertDeepEqual(result.accumulatedCost, 0,
            'Accumulated cost should reset to 0 at renewal time');
            
        // 4. Additional cost after reset (should start fresh)
        sp(params.counterKey, params.model, params.costs.additional,
            params.startDate, params.renewalPeriod, null, params.quota);
        result = context.getResponse().body;
        assertDeepEqual(result.accumulatedCost, params.costs.additional,
            'After reset, should start accumulating from new cost');
    } finally {
        global.Date = originalDate;
    }
});

/**
 * Test Suite: End Date
 */
runner.addTest('Respect end date', async (sp, context) => {
    const params = {
        counterKey: 'test-key-4',
        model: 'gpt-4',
        costs: {
            initial: 40.0,
            additional: 30.0
        },
        startDate: '2024-01-01T00:00:00Z',
        endDate: '2024-01-02T00:00:00Z',
        quota: 100,
        times: {
            initial: '2024-01-01T12:00:00Z',    // Within window
            expired: '2024-01-02T00:00:01Z'     // After end date
        }
    };
    logTestParams('End Date', params);
    
    const originalDate = global.Date;
    const mockDate = (dateString) => {
        global.Date = class extends Date {
            constructor() {
                super();
                return new originalDate(dateString);
            }
            static now() {
                return new originalDate(dateString).getTime();
            }
        };
    };
    
    try {
        // Initial cost
        mockDate(params.times.initial);
        sp(params.counterKey, params.model, params.costs.initial,
            params.startDate, null, params.endDate, params.quota);
        const result = context.getResponse().body;
        assertDeepEqual(result.accumulatedCost, params.costs.initial,
            'Initial cost not set correctly');
        
        // Try to add cost after end date
        mockDate(params.times.expired);
        try {
            sp(params.counterKey, params.model, params.costs.additional,
                params.startDate, null, params.endDate, params.quota);
            throw new Error('Should have failed - after end date');
        } catch (error) {
            if (error.message === 'Should have failed - after end date') {
                throw error;  // Re-throw if it's our error
            }
            // Otherwise it's the expected error from the stored procedure
        }
    } finally {
        global.Date = originalDate;
    }
});

/**
 * Test Suite: Cost Accumulation
 */
runner.addTest('Accumulate costs within renewal period', async (sp, context) => {
    const now = new Date();
    const baseParams = {
        counterKey: 'test-key-3',
        model: 'gpt-4',
        startDate: now.toISOString(),
        renewalPeriod: 2592000,
        endDate: null,
        quota: 100
    };
    
    const updates = [
        { ...baseParams, currentCost: 10.0, step: 'Initial' },
        { ...baseParams, currentCost: 15.0, step: 'Second update' },
        { ...baseParams, currentCost: 25.0, step: 'Third update' }
    ];
    
    logTestParams('Cost Accumulation', updates);
    
    for (const update of updates) {
        sp(update.counterKey, update.model, update.currentCost, update.startDate, 
           update.renewalPeriod, update.endDate, update.quota);
    }
    const result = context.getResponse().body;
    
    assertDeepEqual(result.accumulatedCost, 50.0, 'Cost accumulation failed');
});

/**
 * Test Suite: Input Validation
 */
runner.addTest('Validate required parameters', async (sp) => {
    const testCases = [
        { args: ['', 'gpt-4', 10, null, null, null, 100], error: 'counterKey and model are required' },
        { args: ['test-key', '', 10, null, null, null, 100], error: 'counterKey and model are required' },
        { args: ['test-key', 'gpt-4', -1, null, null, null, 100], error: 'currentCost must be a non-negative' },
        { args: ['test-key', 'gpt-4', 10, null, null, null, 0], error: 'quota must be a positive' },
        { args: ['test-key', 'gpt-4', 10, null, null, null, -1], error: 'quota must be a positive' }
    ];
    logTestParams('Input Validation', testCases);
    for (const testCase of testCases) {
        try {
            sp(...testCase.args);
            throw new Error(`Should have failed with: ${testCase.error}`);
        } catch (error) {
            if (!error.message.includes(testCase.error)) {
                throw error;
            }
        }
    }
    throw createExpectedError('All input validation tests passed');
});

/**
 * Test Suite: Quota Management
 */
runner.addTest('Enforce quota limits', async (sp, context) => {
    const now = new Date();
    const quota = 100;
    const testCases = [
        { 
            initial: 80, 
            additional: 30,  // This will make total 110, exceeding quota
            shouldFail: true, 
            desc: 'Exceeds quota after accumulation'
        },
        { 
            initial: 50, 
            additional: 40,  // Total 90, under quota
            shouldFail: false, 
            desc: 'Stays under quota'
        },
        { 
            initial: 95, 
            additional: 10,  // Total 105, exceeds quota
            shouldFail: true, 
            desc: 'Slightly over quota'
        },
        { 
            initial: 0, 
            additional: 100, // Exactly at quota
            shouldFail: false, 
            desc: 'Exactly at quota'
        }
    ];
    logTestParams('Quota Limits', testCases);
    
    for (const [index, testCase] of testCases.entries()) {
        const key = `test-key-quota-${index}`;
        
        try {
            // Create initial document
            sp(key, 'gpt-4', testCase.initial, now.toISOString(), 2592000, null, quota);
            
            // Try to add additional cost
            sp(key, 'gpt-4', testCase.additional, now.toISOString(), 2592000, null, quota);
            
            if (testCase.shouldFail) {
                throw new Error(`Should have failed quota check for ${key} (${testCase.desc})`);
            }
            
            // Verify final cost if success expected
            const result = context.getResponse().body;
            assertDeepEqual(result.accumulatedCost, testCase.initial + testCase.additional, 
                `Accumulated cost incorrect for ${key}`);
                
        } catch (error) {
            if (testCase.shouldFail && !error.message.includes('exceeds quota')) {
                throw error;
            }
            if (!testCase.shouldFail) {
                throw error;
            }
        }
    }
});

/**
 * Test Suite: Edge Cases
 */
runner.addTest('Handle zero cost updates', async (sp, context) => {
    const now = new Date();
    const params = {
        counterKey: 'test-key-zero',
        model: 'gpt-4',
        initialCost: 50.0,
        updateCost: 0,
        startDate: now.toISOString(),
        renewalPeriod: 2592000,
        quota: 100
    };
    logTestParams('Zero Cost Update', params);
    
    // Create initial document
    sp(params.counterKey, params.model, params.initialCost, params.startDate, params.renewalPeriod, null, params.quota);
    
    // Update with zero cost
    sp(params.counterKey, params.model, params.updateCost, params.startDate, params.renewalPeriod, null, params.quota);
    
    const result = context.getResponse().body;
    assertDeepEqual(result.accumulatedCost, 50.0, 'Zero cost update should not affect accumulated cost');
});

runner.addTest('Handle quota updates', async (sp, context) => {
    const now = new Date();
    const params = {
        counterKey: 'test-key-quota',
        model: 'gpt-4',
        costs: {
            initial: 50.0,
            additional: 10.0
        },
        quotas: {
            initial: 100,
            updated: 200
        },
        startDate: now.toISOString(),
        renewalPeriod: 2592000
    };
    logTestParams('Quota Update', params);
    
    // Create document with initial quota
    sp(params.counterKey, params.model, params.costs.initial, params.startDate, params.renewalPeriod, null, params.quotas.initial);
    
    // Update with new quota
    sp(params.counterKey, params.model, params.costs.additional, params.startDate, params.renewalPeriod, null, params.quotas.updated);
    
    const result = context.getResponse().body;
    assertDeepEqual(result.quota, 200, 'Quota should be updateable');
    assertDeepEqual(result.accumulatedCost, 60.0, 'Cost should accumulate with new quota');
});

// Run all tests
runner.runTests().catch(console.error);

// Mock collection for local testing
const collection = {
    _docs: new Map(),
    readDocument: function(docId) {
        if (!this._docs.has(docId)) {
            throw new Error("Document not found");
        }
        return this._docs.get(docId);
    },
    replaceDocument: function(docId, doc) {
        this._docs.set(docId, doc);
        return true;
    },
    createDocument: function(doc) {
        this._docs.set(doc.id, doc);
        return true;
    },
    clear: function() {
        this._docs.clear();
    }
};

// Helper functions
function runTest(name, fn) {
    console.log(`\n=== ${name} ===`);
    try {
        fn();
        console.log("✅ Test passed");
    } catch (e) {
        console.log("❌ Test failed:", e.message);
    }
}

function assertThrows(fn, expectedError) {
    try {
        fn();
        throw new Error("Expected to throw but did not");
    } catch (e) {
        if (!e.message.includes(expectedError)) {
            throw new Error(`Expected error with "${expectedError}" but got: ${e.message}`);
        }
    }
}

function assertEqual(actual, expected, message) {
    if (actual !== expected) {
        throw new Error(`${message}: expected ${expected} but got ${actual}`);
    }
}

// Test suite
function runTests() {
    const now = new Date();
    const nowISO = now.toISOString();
    const dayInSeconds = 86400;
    
    // Before each test
    beforeEach = () => {
        collection.clear();
        global.getContext = () => ({ getCollection: () => collection });
    };

    // Test 1: Basic quota enforcement
    runTest("Basic Quota Test", () => {
        beforeEach();
        const updateAccumulatedCost = require("../terraform/cosmos_stored_procedure_updatecost");
        
        updateAccumulatedCost("test1", "gpt-4", 5, nowISO, null, null, 10);
        updateAccumulatedCost("test1", "gpt-4", 3, nowISO, null, null, 10);
        
        const doc = collection.readDocument("gpt-4_test1");
        assertEqual(doc.accumulatedCost, 8, "Accumulated cost should be 8");
        
        assertThrows(
            () => updateAccumulatedCost("test1", "gpt-4", 3, nowISO, null, null, 10),
            "exceeded quota"
        );
    });

    // Test 2: Daily renewal
    runTest("Daily Renewal Test", () => {
        beforeEach();
        const updateAccumulatedCost = require("../terraform/cosmos_stored_procedure_updatecost");
        
        // Set start date to 2 days ago
        const twoDaysAgo = new Date(now.getTime() - 2 * dayInSeconds * 1000).toISOString();
        
        // First period
        updateAccumulatedCost("test2", "gpt-4", 4, twoDaysAgo, dayInSeconds, null, 5);
        let doc = collection.readDocument("gpt-4_test2");
        assertEqual(doc.accumulatedCost, 4, "First period cost should be 4");
        
        // Should reset for new period
        updateAccumulatedCost("test2", "gpt-4", 3, twoDaysAgo, dayInSeconds, null, 5);
        doc = collection.readDocument("gpt-4_test2");
        assertEqual(doc.accumulatedCost, 3, "Cost should reset in new period");
    });

    // Test 3: Future start date
    runTest("Future Start Date Test", () => {
        beforeEach();
        const updateAccumulatedCost = require("../terraform/cosmos_stored_procedure_updatecost");
        
        const tomorrow = new Date(now.getTime() + dayInSeconds * 1000).toISOString();
        
        assertThrows(
            () => updateAccumulatedCost("test3", "gpt-4", 1, tomorrow, null, null, 10),
            "before the start date"
        );
    });

    // Test 4: Past end date
    runTest("Past End Date Test", () => {
        beforeEach();
        const updateAccumulatedCost = require("../terraform/cosmos_stored_procedure_updatecost");
        
        const yesterday = new Date(now.getTime() - dayInSeconds * 1000).toISOString();
        
        assertThrows(
            () => updateAccumulatedCost("test4", "gpt-4", 1, nowISO, null, yesterday, 10),
            "after the end date"
        );
    });

    // Test 5: Multiple renewals
    runTest("Multiple Renewals Test", () => {
        beforeEach();
        const updateAccumulatedCost = require("../terraform/cosmos_stored_procedure_updatecost");
        
        // Set start date to 5 days ago
        const fiveDaysAgo = new Date(now.getTime() - 5 * dayInSeconds * 1000).toISOString();
        
        // Should be in a new period
        updateAccumulatedCost("test5", "gpt-4", 3, fiveDaysAgo, dayInSeconds, null, 5);
        const doc = collection.readDocument("gpt-4_test5");
        assertEqual(doc.accumulatedCost, 3, "Cost should be in current period only");
    });

    // Test 6: Update existing document
    runTest("Update Existing Test", () => {
        beforeEach();
        const updateAccumulatedCost = require("../terraform/cosmos_stored_procedure_updatecost");
        
        // Create initial document
        updateAccumulatedCost("test6", "gpt-4", 2, nowISO, null, null, 10);
        
        // Update quota and add cost
        updateAccumulatedCost("test6", "gpt-4", 3, nowISO, null, null, 15);
        const doc = collection.readDocument("gpt-4_test6");
        assertEqual(doc.quota, 15, "Quota should be updated");
        assertEqual(doc.accumulatedCost, 5, "Costs should be accumulated");
    });

    // Test 7: Renewal period change
    runTest("Renewal Period Change Test", () => {
        beforeEach();
        const updateAccumulatedCost = require("../terraform/cosmos_stored_procedure_updatecost");
        
        // Start with daily renewal
        updateAccumulatedCost("test7", "gpt-4", 2, nowISO, dayInSeconds, null, 10);
        
        // Change to weekly renewal
        updateAccumulatedCost("test7", "gpt-4", 3, nowISO, dayInSeconds * 7, null, 10);
        const doc = collection.readDocument("gpt-4_test7");
        assertEqual(doc.renewalPeriod, dayInSeconds * 7, "Renewal period should be updated");
    });
}

// Run all tests
runTests();
