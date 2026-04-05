\# Architecture



\## Overview



This repository demonstrates a selective deployment approach for Azure Data Factory (ADF).



Azure Data Factory deployment is normally state-based. In practice, that means when a deployment is generated from a branch or publish output, the resulting template represents the full current state of the factory rather than only the feature a developer intends to promote.



That behavior works well for simple release flows, but it becomes difficult in environments where multiple features are being developed, tested, and promoted in parallel.



This project addresses that gap by using a Python-based utility to identify a deployable subset of ADF artifacts and package only the resources required for a selected feature or pipeline scope.



\---



\## Problem Statement



In a shared ADF repository, multiple teams or developers often work on different features at the same time.



A common scenario looks like this:



\- Feature 100 has already been promoted to lower environments and is still pending validation in a higher environment.

\- Feature 200 is completed later, but is fully validated and ready for production.

\- Because ADF deployment is based on factory state, promoting Feature 200 may also include Feature 100 and any other in-progress changes present in the current state.



This creates a challenge:



\- Teams cannot easily release only the intended feature

\- Unrelated pipelines or dependencies may get promoted together

\- Release coordination becomes harder as the number of parallel workstreams increases



\---



\## Solution Approach



The solution implemented in this repository introduces a selective deployment pattern.



Instead of promoting the entire ADF state, the utility:



1\. starts with a selected pipeline or feature scope

2\. analyzes dependencies

3\. identifies the minimum required ADF resources

4\. Stage only those resources for deployment

5\. optionally filters out infrastructure-managed resources that should not be promoted as part of the feature deployment



This allows release pipelines to operate on a curated subset rather than the full factory state.



\---



\## High-Level Flow



```text

Developer selects target pipeline(s)

\&#x20;           |

\&#x20;           v

The selective deployment utility analyzes dependencies

\&#x20;           |

\&#x20;           v

Required ADF artifacts are copied into a staging area

\&#x20;           |

\&#x20;           v

Optional filtering removes non-feature resources

\&#x20;           |

\&#x20;           v

Curated deployment package is generated

\&#x20;           |

\&#x20;           v

Selected feature is promoted without deploying unrelated changes


